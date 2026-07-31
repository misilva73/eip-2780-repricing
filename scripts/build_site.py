#!/usr/bin/env python3
"""Render the EIP-2780 repricing dashboard from data/results.json into docs/.

Reads the analysis artifact (data/results.json), renders the Jinja2 templates in
site_src/templates/ into docs/, embeds the data verbatim as docs/data.js
(window.DASHBOARD_DATA = ...) so the page needs no runtime fetch, and copies the
static assets. Run from the repo root: ``python scripts/build_site.py``.

The input path can be overridden with the RESULTS_JSON env var (handy for testing
against a synthetic fixture without touching data/results.json).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Paths are resolved relative to this script so the build works from the repo root.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_RESULTS_JSON = REPO_ROOT / "data" / "results.json"
RUNS_DIR = REPO_ROOT / "data" / "runs"
TEMPLATES_DIR = REPO_ROOT / "site_src" / "templates"
ASSETS_DIR = REPO_ROOT / "site_src" / "assets"
SITE_DIR = REPO_ROOT / "docs"

ASSETS = ["style.css", "charts.js", "trends.js"]

# Human-readable labels for the raw benchmarkoor case_ids. The case_id stays the
# canonical key everywhere in the pipeline (it groups the NNLS fits and is what
# results.json records); these labels are display-only. charts.js carries the same
# map for axis ticks — keep the two in sync. The mapping is documented in
# site_src/templates/methodology.html ("The four receiver cases").
CASE_LABELS = {
    "diff_to_contract": "Contract",
    "diff_to_existent": "EOA",
    "diff_to_nonexistent": "Non-existent",
    "diff_to_self": "Self",
    "diff_to_unique_code_jumpdest_contract": "Contract (jumpdest)",
    "diff_to_contract_minimal": "Contract (minimal)",
    "diff_to_contract_same_max": "Contract (24KB, same code)",
    "diff_to_contract_diff_max": "Contract (24KB, unique code)",
    "diff_to_delegated_contract_diff": "Delegated (24KB, unique code)",
}


def case_label(case_id: str) -> str:
    """Map a raw case_id to its readable label, falling back to the id itself."""
    return CASE_LABELS.get(case_id, case_id)


# Cases kept out of the dashboard's charts, its Summary section and the worst-case
# highlight — but still fit by analysis.py and still listed in full in both detail
# tables. This is a presentation filter only: results.json / data/runs/*.json are
# untouched, so the exclusion applies uniformly to every archived run page (older
# runs included) and can be reverted by emptying this set and re-running `make site`.
# charts.js carries the same set for the client-side chart filtering — keep in sync.
EXCLUDED_CASES = {"diff_to_unique_code_jumpdest_contract", "diff_to_contract"}

# The Trends page has its own, smaller exclusion set: it drops diff_to_contract but
# still charts the jumpdest case, so the two surfaces differ on purpose. Applied in
# collect_trends() — that page's series (including its binding worst case) are built
# server-side, so trends.js needs no filter of its own.
TRENDS_EXCLUDED_CASES = {"diff_to_contract"}

# summary key -> param name, mirroring analysis.py build_summary().
SUMMARY_PARAMS = {
    "zero_value_transfer": "ZERO_VALUE_TRANSFER",
    "value_transfer": "VALUE_TRANSFER",
    "tx_value_cost": "TX_VALUE_COST",
}


def included_rows(rows: list, excluded: set = EXCLUDED_CASES) -> list:
    """Drop excluded-case rows from a new_gas-shaped list."""
    return [r for r in rows if r.get("case_id") not in excluded]


def rebuild_worst_cases(new_gas_rows: list, excluded: set = EXCLUDED_CASES) -> list:
    """Highest-gas row per param over the non-excluded cases.

    Same rule as analysis.py build_worst_cases() (max new_gas_rounded per param),
    re-derived here so each page's worst case matches what its charts show. Rows
    with no gas value can't win and are skipped."""
    best: dict = {}
    for row in included_rows(new_gas_rows, excluded):
        param = row.get("param")
        gas = row.get("new_gas_rounded")
        if not param or gas is None:
            continue
        if param not in best or gas > best[param]["new_gas_rounded"]:
            best[param] = row
    return [best[p] for p in sorted(best)]


def rebuild_summary(worst_case_overall: list, stored: dict) -> dict:
    """Summary block recomputed from the non-excluded worst cases.

    Mirrors analysis.py build_summary(): per-param headline plus the R² <= 0.5 and
    p > 0.05 caveats for the worst-case drivers. ``stored`` (the run's own summary)
    supplies the reference gas, so the 21000/9000 anchors stay in analysis.py."""
    by_param = {r["param"]: r for r in worst_case_overall}
    summary: dict = {}
    caveats = []
    pvalue_caveats = []

    for key, param in SUMMARY_PARAMS.items():
        row = by_param.get(param)
        if row is None:
            summary[key] = None
            continue
        current = row.get("current_gas") or ((stored.get(key) or {}).get("current_gas"))
        new_gas = int(row["new_gas_rounded"])
        change_pct = (new_gas / current - 1) * 100 if current else None
        summary[key] = {
            "new_gas": new_gas,
            "client_name": row.get("client_name"),
            "case_id": row.get("case_id"),
            "rsquared": row.get("rsquared"),
            "pvalue": row.get("pvalue"),
            "current_gas": int(current) if current else None,
            "change_pct": change_pct,
            "direction": "higher" if change_pct and change_pct > 0 else "lower",
        }
        rsq = row.get("rsquared")
        pval = row.get("pvalue")
        common = {
            "param": param,
            "client_name": row.get("client_name"),
            "case_id": row.get("case_id"),
        }
        if rsq is not None and rsq <= 0.5:
            caveats.append({**common, "rsquared": rsq})
        if pval is not None and pval > 0.05:
            pvalue_caveats.append({**common, "pvalue": pval})

    # Sorted by param, matching the order analysis.py's caveats come out in.
    summary["caveats"] = sorted(caveats, key=lambda c: c["param"])
    summary["pvalue_caveats"] = sorted(pvalue_caveats, key=lambda c: c["param"])
    return summary


# --------------------------------------------------------------------------- #
# Goal targets (the Summary section's single table)
# --------------------------------------------------------------------------- #
# EIP-2780 replaces the flat 21000 with a sum of components, so what a transfer
# *should* cost depends on which receiver it hits. TX_VALUE_COST is the EIP's
# marginal value-move charge (21000 - 15000).
TX_BASE_COST = 12000
COLD_ACCOUNT_ACCESS = 3000
TX_VALUE_COST_GOAL = 6000

# A cell reads green at or under its goal, amber up to this far over, red beyond.
GOAL_MID_MARGIN = 0.25

# The components table rendered above the goals, so the sums in the Goal column
# are readable without leaving the page.
GOAL_COMPONENTS = [
    ("TX_BASE_COST", TX_BASE_COST),
    ("COLD_ACCOUNT_ACCESS", COLD_ACCOUNT_ACCESS),
    ("TX_VALUE_COST", TX_VALUE_COST_GOAL),
]

# One entry per goal — and one table row per entry. ``shapes`` names the receiver
# shapes (see goal_variant) the budget has to cover, so a goal spanning several
# receiver cases shows its **worst** case in each cell. The divergence is all in
# how many accounts a transfer touches: a self-transfer touches no second account,
# a delegated receiver is two cold account accesses (the delegating account and
# the one it points at) instead of one. Order here is the table's row order.
GOAL_SPECS = [
    {
        "param": "ZERO_VALUE_TRANSFER",
        "shapes": ("self",),
        "goal": TX_BASE_COST,
        "name": "Transfer to self",
        "formula": "TX_BASE_COST",
    },
    {
        "param": "ZERO_VALUE_TRANSFER",
        "shapes": ("standard",),
        "goal": TX_BASE_COST + COLD_ACCOUNT_ACCESS,
        "name": "No-value transfer",
        "formula": "TX_BASE_COST + COLD_ACCOUNT_ACCESS",
    },
    {
        # Every non-delegated receiver, self included: per the goal spec a value
        # transfer is priced at 21000 whatever it hits.
        "param": "VALUE_TRANSFER",
        "shapes": ("self", "standard"),
        "goal": TX_BASE_COST + COLD_ACCOUNT_ACCESS + TX_VALUE_COST_GOAL,
        "name": "Transfer",
        "formula": "TX_BASE_COST + COLD_ACCOUNT_ACCESS + TX_VALUE_COST",
    },
    {
        "param": "ZERO_VALUE_TRANSFER",
        "shapes": ("delegated",),
        "goal": TX_BASE_COST + 2 * COLD_ACCOUNT_ACCESS,
        "name": "No-value transfer to delegated account",
        "formula": "TX_BASE_COST + 2 × COLD_ACCOUNT_ACCESS",
    },
    {
        "param": "VALUE_TRANSFER",
        "shapes": ("delegated",),
        "goal": TX_BASE_COST + 2 * COLD_ACCOUNT_ACCESS + TX_VALUE_COST_GOAL,
        "name": "Transfer to delegated account",
        "formula": "TX_BASE_COST + 2 × COLD_ACCOUNT_ACCESS + TX_VALUE_COST",
    },
]

# Params with a goal. TX_VALUE_COST has none — it is a component of the goals
# above, not a target of its own.
GOAL_PARAMS = frozenset(spec["param"] for spec in GOAL_SPECS)

# Order the cases a goal covers are listed in, cheapest receiver first. A case not
# listed here still shows — it just sorts last, alphabetically.
GOAL_CASE_ORDER = (
    "diff_to_self",
    "diff_to_nonexistent",
    "diff_to_existent",
    "diff_to_contract_minimal",
    "diff_to_contract_same_max",
    "diff_to_contract_diff_max",
    "diff_to_unique_code_jumpdest_contract",
    "diff_to_contract",
    "diff_to_delegated_contract_diff",
)


def goal_variant(case_id: str) -> str:
    """Which of the three receiver shapes a case falls into."""
    if "delegated" in case_id:
        return "delegated"
    if case_id == "diff_to_self":
        return "self"
    return "standard"


def collect_goals(new_gas_rows: list) -> dict:
    """Per-client measured gas against each EIP-2780 goal.

    One row per ``GOAL_SPECS`` entry and one column per client. Where a goal
    covers several receiver cases the cell holds that client's **worst** (highest)
    case, since the budget has to cover all of them; the cell records which case
    that was. Cells are tinted against the goal: green at or under it, amber up to
    ``GOAL_MID_MARGIN`` over, red beyond. Callers pass the *charted* rows (excluded
    cases already dropped), so the table covers exactly what the charts below it
    show. A client with no fit for any of a goal's cases leaves a no-data cell.
    """
    value: dict = {}
    clients: set = set()
    cases: set = set()
    for row in new_gas_rows:
        param = row.get("param")
        client = row.get("client_name")
        case = row.get("case_id")
        gas = row.get("new_gas_rounded")
        if param not in GOAL_PARAMS or not client or not case or gas is None:
            continue
        value[(param, case, client)] = int(gas)
        clients.add(client)
        cases.add(case)

    ordered_clients = sorted(clients)
    ordered_cases = sorted(
        cases,
        key=lambda c: (
            (GOAL_CASE_ORDER.index(c), "")
            if c in GOAL_CASE_ORDER
            else (len(GOAL_CASE_ORDER), c)
        ),
    )

    rows: list = []
    for spec in GOAL_SPECS:
        param, goal = spec["param"], spec["goal"]
        covered = [c for c in ordered_cases if goal_variant(c) in spec["shapes"]]
        cells = []
        for client in ordered_clients:
            found = [
                (value[(param, case, client)], case)
                for case in covered
                if (param, case, client) in value
            ]
            if not found:
                cells.append({"client": client, "gas": None, "cls": "goal-nodata"})
                continue
            gas, worst_case = max(found)
            over_pct = (gas / goal - 1) * 100
            if over_pct <= 0:
                cls = "goal-pass"
            elif over_pct <= GOAL_MID_MARGIN * 100:
                cls = "goal-mid"
            else:
                cls = "goal-fail"
            cells.append(
                {
                    "client": client,
                    "gas": gas,
                    "cls": cls,
                    "over_pct": over_pct,
                    "worst_case": worst_case,
                    "worst_case_label": case_label(worst_case),
                    "n_cases": len(found),
                }
            )
        # A goal none of the clients has a fit for carries no information.
        if all(c["gas"] is None for c in cells):
            continue
        rows.append(
            {
                "param": param,
                "goal": goal,
                "name": spec["name"],
                "formula": spec["formula"],
                "cases": [{"case_id": c, "label": case_label(c)} for c in covered],
                "cells": cells,
            }
        )

    return {
        "clients": ordered_clients,
        "rows": rows,
        "components": [{"name": n, "value": v} for n, v in GOAL_COMPONENTS],
        "mid_margin_pct": int(GOAL_MID_MARGIN * 100),
    }


def git_commit() -> str:
    """Return the current short commit hash, or "unknown" on failure."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def load_results() -> dict:
    results_path = Path(os.environ.get("RESULTS_JSON", DEFAULT_RESULTS_JSON))
    if not results_path.is_file():
        print(
            f"error: results data not found at {results_path}\n"
            "Run `make analyze` first (or set RESULTS_JSON to a valid file).",
            file=sys.stderr,
        )
        sys.exit(1)
    with results_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def run_id_for(data: dict) -> str:
    """Return the run's id, synthesizing one from window/suite when absent.

    analyze stamps ``meta.run_id``; the fallback keeps a pre-archive results.json
    (or any older artifact without the field) renderable as a single run. Mirrors
    the derivation in analysis.py ``_make_run_id``."""
    meta = data.get("meta", {}) or {}
    rid = meta.get("run_id")
    if rid:
        return str(rid)
    window = meta.get("window") or {}
    stamp = re.sub(
        r"[:\-]", "", str(window.get("end") or meta.get("generated_at") or "run")
    )
    suite = meta.get("suite")
    token = "_" + re.split(r"[,\s]+", str(suite).strip())[0] if suite else ""
    return f"{stamp}{token}"


def run_label(data: dict) -> str:
    """Human-readable dropdown label: the data-window end as ``YYYY-MM-DD HH:MM``."""
    meta = data.get("meta", {}) or {}
    end = (meta.get("window") or {}).get("end") or meta.get("generated_at")
    if not end:
        return run_id_for(data)
    s = str(end).replace("Z", "")
    if "T" in s:
        date, _, time = s.partition("T")
        return f"{date} {time[:5]}".strip()
    return s


def load_runs() -> list:
    """Load every archived run from data/runs/, newest first.

    Falls back to the committed results.json as a single run when the archive is
    empty/absent, so the site still renders before the first archived analyze."""
    runs = []
    if RUNS_DIR.is_dir():
        for path in sorted(RUNS_DIR.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as fh:
                    runs.append(json.load(fh))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"warning: skipping {path}: {exc}", file=sys.stderr)
    if not runs:
        runs = [load_results()]
    runs.sort(key=run_id_for, reverse=True)
    return runs


def build_run_index(runs: list) -> list:
    """One dropdown entry per run: id, label, page href and data-file name.

    Index 0 is the latest and owns index.html / data.js; the rest get
    run-<id>.html / data-<id>.js. All output is flat under docs/ so the hrefs are
    plain relative links."""
    index = []
    for i, data in enumerate(runs):
        rid = run_id_for(data)
        if i == 0:
            index.append(
                {
                    "run_id": rid,
                    "label": f"{run_label(data)} (latest)",
                    "href": "index.html",
                    "data_file": "data.js",
                }
            )
        else:
            index.append(
                {
                    "run_id": rid,
                    "label": run_label(data),
                    "href": f"run-{rid}.html",
                    "data_file": f"data-{rid}.js",
                }
            )
    return index


def collect_trends(runs: list) -> dict:
    """Per-(client, case) gas/runtime series across all runs, for the Trends page.

    ``load_runs()`` returns newest-first; here we reverse to oldest→newest so the
    run axis reads chronologically. Unlike the upstream eip-8038 page (one selected
    fit per (param, client)), 2780 keeps the receiver-``case`` dimension, so each
    trend line is keyed by (param, client, case) — the same grid the dashboard
    charts already facet by. Per run we read every ``new_gas`` row (the per-(client,
    case) converted gas) outside TRENDS_EXCLUDED_CASES, and re-derive the binding
    worst-case row (the one that sets each param's proposal) from those same rows so
    it can never name a case this page doesn't chart. A run missing a (param, client,
    case) leaves a ``None`` gap; clients/cases are unioned across runs.

    ``poor`` mirrors analysis.py's caveat thresholds (R² <= 0.5 or p-value > 0.05):
    a true value flags the underlying fit as low-confidence.

    ``anchor_eras`` groups consecutive runs by their ``meta.anchor_rate``. Gas is
    runtime scaled by that anchor, and archived runs keep whatever anchor they were
    analyzed under (raw parquet for old windows is gone, so they can't be recomputed),
    so a change in ANCHOR_RATE puts a step in every gas series here. More than one era
    means the page shows a caveat; the runtime series are anchor-independent."""
    chron = list(reversed(runs))
    n = len(chron)
    gas: dict = {}
    runtime: dict = {}
    poor: dict = {}
    binding: dict = {}
    params: list = []
    clients: set = set()
    cases: set = set()

    def cell(store: dict, param: str, client: str, case: str) -> list:
        return (
            store.setdefault(param, {})
            .setdefault(client, {})
            .setdefault(case, [None] * n)
        )

    for i, data in enumerate(chron):
        rows = included_rows(data.get("new_gas", []) or [], TRENDS_EXCLUDED_CASES)
        for row in rows:
            param = row.get("param")
            client = row.get("client_name")
            case = row.get("case_id")
            if not (param and client and case):
                continue
            if param not in params:
                params.append(param)
            clients.add(client)
            cases.add(case)
            ng = row.get("new_gas_rounded")
            rt = row.get("runtime_ms")
            cell(gas, param, client, case)[i] = int(ng) if ng is not None else None
            cell(runtime, param, client, case)[i] = (
                float(rt) if rt is not None else None
            )
            rsq = row.get("rsquared")
            pval = row.get("pvalue")
            cell(poor, param, client, case)[i] = bool(
                (rsq is not None and rsq <= 0.5) or (pval is not None and pval > 0.05)
            )

        # Re-derived, not read from the run's stored worst_case_overall: that one
        # ranks over every case, including the ones this page excludes.
        for row in rebuild_worst_cases(rows, TRENDS_EXCLUDED_CASES):
            param = row.get("param")
            if not param:
                continue
            val = row.get("new_gas_rounded")
            binding.setdefault(param, [None] * n)[i] = {
                "value": int(val) if val is not None else None,
                "client": row.get("client_name"),
                "case": row.get("case_id"),
            }

    anchor_eras: list = []
    for data in chron:
        rate = (data.get("meta", {}) or {}).get("anchor_rate")
        mgas = round(float(rate) / 1e6) if rate else None
        label = run_label(data)
        if anchor_eras and anchor_eras[-1]["mgas"] == mgas:
            anchor_eras[-1]["last"] = label
            anchor_eras[-1]["count"] += 1
        else:
            anchor_eras.append(
                {"mgas": mgas, "first": label, "last": label, "count": 1}
            )

    return {
        "runs": [{"run_id": run_id_for(d), "label": run_label(d)} for d in chron],
        "anchor_eras": anchor_eras,
        "clients": sorted(clients),
        "cases": sorted(cases),
        "params": params,  # discovery order, e.g. ZERO_VALUE_TRANSFER, VALUE_TRANSFER, TX_VALUE_COST
        "gas": gas,
        "runtime": runtime,
        "poor": poor,
        "binding": binding,
    }


def clear_stale_outputs() -> None:
    """Drop previously generated per-run pages/data so a removed run leaves no
    orphan behind. Leaves index.html/data.js and the static assets untouched."""
    for pattern in ("run-*.html", "data-*.js"):
        for path in SITE_DIR.glob(pattern):
            path.unlink()


def main() -> None:
    runs = load_runs()
    run_index = build_run_index(runs)
    commit = git_commit()

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    clear_stale_outputs()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["case_label"] = case_label
    index_tpl = env.get_template("index.html")

    written = []
    # One self-contained dashboard page per run. The dropdown (server-rendered
    # from run_index) just navigates between them; charts.js reads the per-page
    # data file's window.DASHBOARD_DATA, so no run-switching JS is needed.
    for i, (data, entry) in enumerate(zip(runs, run_index)):
        runs_for_page = [
            {**r, "is_current": r["run_id"] == entry["run_id"]} for r in run_index
        ]
        # The Summary section and the worst-case highlight are re-derived from the
        # non-excluded cases (see EXCLUDED_CASES) so they agree with the charts; the
        # detail tables below them still render every row of `new_gas` / `results`.
        new_gas = data.get("new_gas", []) or []
        charted = included_rows(new_gas)
        worst_case_overall = rebuild_worst_cases(new_gas)
        context = {
            "data": data,
            "meta": data.get("meta", {}) or {},
            "results": data.get("results", []),
            "new_gas": new_gas,
            "summary_new_gas": charted,
            "goals": collect_goals(charted),
            "worst_case_overall": worst_case_overall,
            "worst_case_by_case": data.get("worst_case_by_case", []),
            "summary": rebuild_summary(
                worst_case_overall, data.get("summary", {}) or {}
            ),
            "commit": commit,
            "runs": runs_for_page,
            "is_latest": i == 0,  # index 0 is the newest run
            "data_file": entry["data_file"],
            "page": "dashboard",
        }
        out_path = SITE_DIR / entry["href"]
        out_path.write_text(index_tpl.render(**context), encoding="utf-8")
        written.append(out_path)

        # Embed the run's data verbatim so charts.js can read it without a fetch().
        data_js = SITE_DIR / entry["data_file"]
        data_js.write_text(
            "window.DASHBOARD_DATA = " + json.dumps(data) + ";\n",
            encoding="utf-8",
        )
        written.append(data_js)

    # Methodology is run-agnostic: render once from the latest run, no selector.
    latest = runs[0] if runs else {}
    methodology_html = env.get_template("methodology.html").render(
        data=latest,
        meta=latest.get("meta", {}) or {},
        commit=commit,
        page="methodology",
    )
    methodology_path = SITE_DIR / "methodology.html"
    methodology_path.write_text(methodology_html, encoding="utf-8")
    written.append(methodology_path)

    # Trends is a cross-run singleton at the docs root (like methodology — no run
    # selector). Its data is embedded inline in the template, so no data-*.js file;
    # the shared footer reads the latest run's meta.
    trends_html = env.get_template("trends.html").render(
        trends=collect_trends(runs),
        meta=latest.get("meta", {}) or {},
        commit=commit,
        page="trends",
    )
    trends_path = SITE_DIR / "trends.html"
    trends_path.write_text(trends_html, encoding="utf-8")
    written.append(trends_path)

    for asset in ASSETS:
        src = ASSETS_DIR / asset
        dst = SITE_DIR / asset
        shutil.copyfile(src, dst)
        written.append(dst)

    print(f"Built site into {SITE_DIR} ({len(runs)} run(s))")
    for path in written:
        print(f"  wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

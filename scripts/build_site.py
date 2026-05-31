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

ASSETS = ["style.css", "charts.js"]

# Human-readable labels for the raw benchmarkoor case_ids. The case_id stays the
# canonical key everywhere in the pipeline (it groups the NNLS fits and is what
# results.json records); these labels are display-only. charts.js carries the same
# map for axis ticks — keep the two in sync. The mapping is documented in
# site_src/templates/methodology.html ("The four receiver cases").
CASE_LABELS = {
    "diff_to_contract": "Contract",
    "diff_to_existent": "EOA",
    "diff_to_nonexistent": "Non-existent",
    "diff_to_unique_code_jumpdest_contract": "Contract (unique code)",
}


def case_label(case_id: str) -> str:
    """Map a raw case_id to its readable label, falling back to the id itself."""
    return CASE_LABELS.get(case_id, case_id)


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
        context = {
            "data": data,
            "meta": data.get("meta", {}) or {},
            "results": data.get("results", []),
            "new_gas": data.get("new_gas", []),
            "worst_case_overall": data.get("worst_case_overall", []),
            "worst_case_by_case": data.get("worst_case_by_case", []),
            "summary": data.get("summary", {}),
            "commit": commit,
            "runs": runs_for_page,
            "is_latest": i == 0,  # index 0 is the newest run
            "data_file": entry["data_file"],
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
    )
    methodology_path = SITE_DIR / "methodology.html"
    methodology_path.write_text(methodology_html, encoding="utf-8")
    written.append(methodology_path)

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

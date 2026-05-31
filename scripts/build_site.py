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
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Paths are resolved relative to this script so the build works from the repo root.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_RESULTS_JSON = REPO_ROOT / "data" / "results.json"
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


def main() -> None:
    data = load_results()
    meta = data.get("meta", {}) or {}

    SITE_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["case_label"] = case_label

    context = {
        "data": data,
        "meta": meta,
        "results": data.get("results", []),
        "new_gas": data.get("new_gas", []),
        "worst_case_overall": data.get("worst_case_overall", []),
        "worst_case_by_case": data.get("worst_case_by_case", []),
        "summary": data.get("summary", {}),
        "commit": git_commit(),
    }

    written = []
    for page in ("index.html", "methodology.html"):
        html = env.get_template(page).render(**context)
        out_path = SITE_DIR / page
        out_path.write_text(html, encoding="utf-8")
        written.append(out_path)

    # Embed the data verbatim so charts.js can read it without a fetch().
    data_js = SITE_DIR / "data.js"
    data_js.write_text(
        "window.DASHBOARD_DATA = " + json.dumps(data) + ";\n",
        encoding="utf-8",
    )
    written.append(data_js)

    for asset in ASSETS:
        src = ASSETS_DIR / asset
        dst = SITE_DIR / asset
        shutil.copyfile(src, dst)
        written.append(dst)

    print(f"Built site into {SITE_DIR}")
    for path in written:
        print(f"  wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

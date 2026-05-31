#!/usr/bin/env python3
"""Delete an archived run and re-render the site.

Removes ``data/runs/<RUN_ID>.json``. If the deleted run was the latest (newest
run_id), the next-newest remaining run is promoted by copying it over
``data/results.json`` so the committed "latest pointer" stays truthful and
``docs/index.html`` matches it. Then ``build_site.py`` is invoked to re-render —
stale ``docs/run-*.html`` / ``docs/data-*.js`` are cleared by that build.

Usage (typically via ``make clean-run RUN_ID=<id>``):

    python scripts/clean_run.py <RUN_ID>

Run ids are the ``data/runs/*.json`` filenames (also shown in the dashboard
footer and run dropdown).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RUNS_DIR = REPO_ROOT / "data" / "runs"
RESULTS_JSON = REPO_ROOT / "data" / "results.json"
BUILD_SITE = SCRIPT_DIR / "build_site.py"


def _run_id_of(path: Path) -> str:
    """Newest-first sort key: prefer the stamped run_id, fall back to filename."""
    try:
        with path.open(encoding="utf-8") as fh:
            rid = (json.load(fh).get("meta", {}) or {}).get("run_id")
    except (json.JSONDecodeError, OSError):
        rid = None
    return str(rid or path.stem)


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].strip():
        print("usage: python scripts/clean_run.py <RUN_ID>", file=sys.stderr)
        return 2
    run_id = argv[0].strip()

    target = RUNS_DIR / f"{run_id}.json"
    if not target.is_file():
        print(f"error: no archived run at {target}", file=sys.stderr)
        existing = (
            sorted(p.stem for p in RUNS_DIR.glob("*.json")) if RUNS_DIR.is_dir() else []
        )
        if existing:
            print("available run ids:", file=sys.stderr)
            for rid in existing:
                print(f"  {rid}", file=sys.stderr)
        return 1

    # Was this the latest (newest) run? Compare against all archived runs.
    all_runs = sorted(RUNS_DIR.glob("*.json"), key=_run_id_of, reverse=True)
    was_latest = bool(all_runs) and all_runs[0] == target

    target.unlink()
    print(f"Deleted {target.relative_to(REPO_ROOT)}")

    # Promote the new newest run to results.json so the latest pointer stays true.
    remaining = sorted(RUNS_DIR.glob("*.json"), key=_run_id_of, reverse=True)
    if was_latest:
        if remaining:
            newest = remaining[0]
            RESULTS_JSON.write_text(
                newest.read_text(encoding="utf-8"), encoding="utf-8"
            )
            print(
                f"Promoted {newest.relative_to(REPO_ROOT)} -> {RESULTS_JSON.relative_to(REPO_ROOT)}"
            )
        else:
            print(
                "warning: no archived runs remain; data/results.json left unchanged "
                "(it still holds the deleted run). Run `make analyze` to refresh.",
                file=sys.stderr,
            )

    # Re-render the site (build_site clears stale run-*.html / data-*.js).
    print("Rebuilding site...")
    return subprocess.run([sys.executable, str(BUILD_SITE)], cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

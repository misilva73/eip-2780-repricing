# EIP-2780 Repricing Dashboard

Derives proposed gas values for EIP-2780 by measuring the end-to-end cost of each
transfer kind directly: `ZERO_VALUE_TRANSFER` (plain transfer, referenced against
21000) and `VALUE_TRANSFER` (value transfer, also referenced against 21000) — plus
the derived `TX_VALUE_COST` (`VALUE_TRANSFER − ZERO_VALUE_TRANSFER`, the marginal
cost of moving value, referenced against 9000). For each `(client, case_id)` it
fits **two independent NNLS models** — one on the `transfer_amount=0` runs, one on
the `transfer_amount=1` runs, each `[const, opcount]` — converts the opcount slopes
to gas at a 100 Mgas/s anchor, picks the worst case per param, and renders a static
GitHub Pages dashboard.

## Pipeline

`make` runs `fetch → analyze → site` (see [Makefile](Makefile)):

- `make fetch`   — `benchmarkoor-fetch` → `data/raw/*.parquet` + `meta.json` (gitignored)
- `make analyze` — [scripts/analysis.py](scripts/analysis.py) → `data/results.json` (latest, committed) **and** archives a copy to `data/runs/<run_id>.json` (committed history)
- `make site`    — [scripts/build_site.py](scripts/build_site.py): `data/runs/*` + `site_src/` → `docs/` (one page per run; latest is `index.html`) plus two run-agnostic singletons, `docs/methodology.html` and `docs/trends.html`

## Run history

The dashboard shows the latest run with a run selector (a banner above the hero)
to switch to previous runs. History accumulates going forward — there is no backfill.

- Each `make analyze` archives its result to `data/runs/<run_id>.json` (committed).
  `run_id` is `meta.run_id`, keyed on the data-window end + suite, so
  re-analyzing the same data **overwrites in place** instead of duplicating.
  `data/results.json` remains the canonical latest pointer (a copy of the newest run).
- `make site` renders one self-contained page per archived run: latest →
  `docs/index.html` + `docs/data.js`; each older run → `docs/run-<id>.html` +
  `docs/data-<id>.js`. The selector is a custom button+listbox (server-rendered
  in [index.html](site_src/templates/index.html); each option is a plain link, so
  switching runs is just navigation between these pages). `charts.js`
  (`initRunDropdown`) only adds open/close + keyboard handling — not a native
  `<select>`, so the open list matches the page font. With a single archived run
  it degrades to a static label. Stale `run-*.html` / `data-*.js` are cleared at
  the start of each build.
- **Delete a run:** `make clean-run RUN_ID=<id>` ([scripts/clean_run.py](scripts/clean_run.py))
  removes the archive file, promotes the next-newest run to `data/results.json`
  if you dropped the latest, and re-renders. Commit the deletion + regenerated `docs/`.
- **Trends page** (`docs/trends.html`) is a cross-run singleton (no run selector):
  `build_site.collect_trends(runs)` aggregates every run's `new_gas` +
  `worst_case_overall` into per-`(param, client, case)` gas/runtime series and a
  binding worst-case series, embedded inline; [trends.js](site_src/assets/trends.js)
  draws Plotly line-charts (colour = client, dash = case) with a since-last-run
  delta table + Δ% bar. No per-run `data-*.js` and no `analysis.py` change — it
  reads the existing per-run JSON only. The since-last-run "Previous" value is
  **backfilled**: a client that skipped run N-2 (e.g. geth missing a run) falls
  back to its most recent earlier run instead of showing a gap. The "Latest" value
  is never backfilled — if a client is absent from the newest run it stays empty.

Needs `secrets.json` at root: `{"BENCHMARKOOR_TOKEN": "bmk_..."}` (gitignored).
Requires `make`, `jq`, Python 3.11+.

## Where to edit

| To change… | Edit | Then run |
| --- | --- | --- |
| data window / suite | [configs/benchmarkoor.yaml](configs/benchmarkoor.yaml) (pinned suite hash) | `make` |
| analysis / outputs | [scripts/analysis.py](scripts/analysis.py) Part B | `make analyze site` |
| page content / layout | `site_src/templates/*.html` | `make site` |
| styles / charts | `site_src/assets/{style.css,charts.js,trends.js}` | `make site` |

## Must not break

- **`docs/` is build output — never hand-edit it.** Edit `site_src/`, rerun `make site`.
  `docs/{*.html,*.js,style.css}` are all generated, including `run-<id>.html`,
  per-run `data-<id>.js`, `methodology.html`, and `trends.html`. Templates extend a
  shared `site_src/templates/base.html`. `methodology.html` and `trends.html` are
  each rendered once from the latest run (run-agnostic, no run selector) — see
  [build_site.py](scripts/build_site.py).
- **`analysis.py` Part A is ported verbatim** from `evm-gas-repricings`
  (`NNLSResults`, `fit_NNLS`, `prepare_non_simple_model_data`,
  `extract_param_values`). Don't refactor it — keep it diffable against upstream.
  All EIP-2780-specific logic lives in Part B. (The upstream
  `fit_NNLS_without_low_diff_runs`/`find_low_diff_runs` adaptive filter was
  dropped — it never triggered on this suite's data.)
- **`opcount` is recomputed**, ignoring benchmarkoor's own column: `JUMP` from
  the trace per contract tx, else `floor(block_gas_limit/21000)` for EOA cases.
- **Column rename:** `test_runtime_ms → run_duration_ms` right after load — the
  ported NNLS code expects the latter.
- **Two fits per `(client, case_id)`** (Part B `build_results_df`): the group is
  split on `transfer_amount` and each subset fit as its own `[const, opcount]`
  NNLS model (`without_*` = zero-value, `with_*` = value). The interaction-term
  `prepare_non_simple_model_data` from Part A is left in place for upstream
  diffability but is **no longer called**.
- **Constants** (`ANCHOR_RATE`, `TX_BASE`, `VALUE_GAS_CURRENT`, `TEST_NAME`) are
  in analysis.py near `# PART B`. `current_gas` reference values come from these:
  `ZERO_VALUE_TRANSFER` and `VALUE_TRANSFER` both reference `TX_BASE` (21000 — a
  value transfer never paid a separate flat charge), and the derived
  `TX_VALUE_COST` (`VALUE_TRANSFER − ZERO_VALUE_TRANSFER`, clamped ≥0; CI via
  interval arithmetic on the two independent fits) references `VALUE_GAS_CURRENT`
  (9000). Note `VALUE_TRANSFER` is now fit directly (the value-subset opcount
  slope), not summed as `TX_BASE + VALUE_GAS`.
- **Each page's data file embeds its run verbatim** as `window.DASHBOARD_DATA` —
  no runtime `fetch()` (avoids project-pages base-path issues). `index.html` loads
  `data.js`; `run-<id>.html` loads `data-<id>.js`. `charts.js` reads whichever is
  loaded. All output is flat under `docs/` so the dropdown's relative links work.

## Deploy

GitHub Pages serves `/docs` on `main`. No CI. After a data/site change, commit
`data/results.json`, the new/changed `data/runs/*.json`, and `docs/`, then push.

**Never create a new git branch unless explicitly asked.** Commit directly to
`main` (the deploy branch) — do not branch first.

## Verify before commit

`make site && (cd docs && python -m http.server)` — check the Dashboard,
Methodology, and Trends pages render, Plotly charts are interactive, tables show
worst-case highlights, footer populated (incl. `generated`). With >1 archived run,
the **Viewing run** selector banner switches pages and the latest reads "(latest)",
and the Trends page's since-last-run delta table + Δ% bar populate (with one run it
shows a "only one run archived" note). `results.json` worst case
currently tracks erigon for all three params (`ZERO_VALUE_TRANSFER` →
`diff_to_unique_code_jumpdest_contract`, `VALUE_TRANSFER` and `TX_VALUE_COST` →
`diff_to_contract`) (this follows the data — re-check after a data refresh).

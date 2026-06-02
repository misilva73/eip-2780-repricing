# EIP-2780 Repricing Dashboard

Derives proposed gas values for EIP-2780's `TX_BASE` (21000) and `VALUE_GAS`
(9000) — plus the derived `VALUE_TRANSFER` (`TX_BASE + VALUE_GAS`, the
end-to-end cost of a value transfer, referenced against `TX_BASE`) — from
`test_ether_transfers_onchain_receivers` benchmark runtimes. Fits NNLS per
`(client, case_id)`, converts coefficients to gas at a 100 Mgas/s anchor, picks
the worst case per param, renders a static GitHub Pages dashboard.

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
  reads the existing per-run JSON only.

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
- **Constants** (`ANCHOR_RATE`, `TX_BASE`, `VALUE_GAS_CURRENT`, `TEST_NAME`) are
  in analysis.py near `# PART B`. `current_gas` reference values come from these.
  `VALUE_TRANSFER` is derived (`TX_BASE + VALUE_GAS` per fit) and references
  `TX_BASE` — there was never a separate flat charge for transfers.
- **Each page's data file embeds its run verbatim** as `window.DASHBOARD_DATA` —
  no runtime `fetch()` (avoids project-pages base-path issues). `index.html` loads
  `data.js`; `run-<id>.html` loads `data-<id>.js`. `charts.js` reads whichever is
  loaded. All output is flat under `docs/` so the dropdown's relative links work.

## Deploy

GitHub Pages serves `/docs` on `main`. No CI. After a data/site change, commit
`data/results.json`, the new/changed `data/runs/*.json`, and `docs/`, then push.

## Verify before commit

`make site && (cd docs && python -m http.server)` — check the Dashboard,
Methodology, and Trends pages render, Plotly charts are interactive, tables show
worst-case highlights, footer populated (incl. `generated`). With >1 archived run,
the **Viewing run** selector banner switches pages and the latest reads "(latest)",
and the Trends page's since-last-run delta table + Δ% bar populate (with one run it
shows a "only one run archived" note). `results.json` worst case
currently tracks besu
`diff_to_unique_code_jumpdest_contract` for all three params (TX_BASE,
VALUE_GAS, VALUE_TRANSFER) (this follows the data — re-check after a data refresh).

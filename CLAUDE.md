# EIP-2780 Repricing Dashboard

Derives proposed gas values for EIP-2780's `TX_BASE` (21000) and `VALUE_GAS`
(9000) from `test_ether_transfers_onchain_receivers` benchmark runtimes. Fits
NNLS per `(client, case_id)`, converts coefficients to gas at a 100 Mgas/s
anchor, picks the worst case per param, renders a static GitHub Pages dashboard.

## Pipeline

`make` runs `fetch → analyze → site` (see [Makefile](Makefile)):

- `make fetch`   — `benchmarkoor-fetch` → `data/raw/*.parquet` + `meta.json` (gitignored)
- `make analyze` — [scripts/analysis.py](scripts/analysis.py) → `data/results.json` (latest, committed) **and** archives a copy to `data/runs/<run_id>.json` (committed history)
- `make site`    — [scripts/build_site.py](scripts/build_site.py): `data/runs/*` + `site_src/` → `docs/` (one page per run; latest is `index.html`)

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

Needs `secrets.json` at root: `{"BENCHMARKOOR_TOKEN": "bmk_..."}` (gitignored).
Requires `make`, `jq`, Python 3.11+.

## Where to edit

| To change… | Edit | Then run |
| --- | --- | --- |
| data window / suite | [configs/benchmarkoor.yaml](configs/benchmarkoor.yaml) (pinned suite hash) | `make` |
| analysis / outputs | [scripts/analysis.py](scripts/analysis.py) Part B | `make analyze site` |
| page content / layout | `site_src/templates/*.html` | `make site` |
| styles / charts | `site_src/assets/{style.css,charts.js}` | `make site` |

## Must not break

- **`docs/` is build output — never hand-edit it.** Edit `site_src/`, rerun `make site`.
  `docs/{*.html,*.js,style.css}` are all generated, including `run-<id>.html` and
  per-run `data-<id>.js`.
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
- **Each page's data file embeds its run verbatim** as `window.DASHBOARD_DATA` —
  no runtime `fetch()` (avoids project-pages base-path issues). `index.html` loads
  `data.js`; `run-<id>.html` loads `data-<id>.js`. `charts.js` reads whichever is
  loaded. All output is flat under `docs/` so the dropdown's relative links work.

## Deploy

GitHub Pages serves `/docs` on `main`. No CI. After a data/site change, commit
`data/results.json`, the new/changed `data/runs/*.json`, and `docs/`, then push.

## Verify before commit

`make site && (cd docs && python -m http.server)` — check both pages render,
Plotly charts are interactive, tables show worst-case highlights, footer
populated (incl. `generated`). With >1 archived run, the **Viewing run** selector
banner switches pages and the latest reads "(latest)". `results.json` worst case
currently tracks besu
`diff_to_unique_code_jumpdest_contract` for both TX_BASE and VALUE_GAS (this
follows the data — re-check after a data refresh).

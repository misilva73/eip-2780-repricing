# EIP-2780 Repricing Dashboard

Derives proposed gas values for EIP-2780's `TX_BASE` (21000) and `VALUE_GAS`
(9000) from `test_ether_transfers_onchain_receivers` benchmark runtimes. Fits
NNLS per `(client, case_id)`, converts coefficients to gas at a 100 Mgas/s
anchor, picks the worst case per param, renders a static GitHub Pages dashboard.

## Pipeline

`make` runs `fetch → analyze → site` (see [Makefile](Makefile)):

- `make fetch`   — `benchmarkoor-fetch` → `data/raw/*.parquet` + `meta.json` (gitignored)
- `make analyze` — [scripts/analysis.py](scripts/analysis.py) → `data/results.json` (committed)
- `make site`    — [scripts/build_site.py](scripts/build_site.py): `results.json` + `site_src/` → `docs/`

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
  `docs/{*.html,data.js,style.css,charts.js}` are all generated.
- **`analysis.py` Part A is ported verbatim** from `evm-gas-repricings`
  (`NNLSResults`, `fit_NNLS*`, `prepare_non_simple_model_data`,
  `extract_param_values`). Don't refactor it — keep it diffable against upstream.
  All EIP-2780-specific logic lives in Part B.
- **`opcount` is recomputed**, ignoring benchmarkoor's own column: `JUMP` from
  the trace per contract tx, else `floor(block_gas_limit/21000)` for EOA cases.
- **Column rename:** `test_runtime_ms → run_duration_ms` right after load — the
  ported NNLS code expects the latter.
- **Constants** (`ANCHOR_RATE`, `TX_BASE`, `VALUE_GAS_CURRENT`, `TEST_NAME`) are
  in analysis.py near `# PART B`. `current_gas` reference values come from these.
- **`data.js` embeds `results.json` verbatim** as `window.DASHBOARD_DATA` — no
  runtime `fetch()` (avoids project-pages base-path issues). `charts.js` reads it.

## Deploy

GitHub Pages serves `/docs` on `main`. No CI. After a data/site change, commit
both `data/results.json` and `docs/`, then push.

## Verify before commit

`make site && (cd docs && python -m http.server)` — check both pages render,
Plotly charts are interactive, tables show worst-case highlights, footer
populated. `results.json` worst case should track besu `diff_to_nonexistent`
(TX_BASE) / `diff_to_existent` (VALUE_GAS).

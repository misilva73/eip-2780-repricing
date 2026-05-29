# EIP-2780 Repricing Dashboard — Implementation Plan

## Context

The notebook [ether-transfers-tx-base-value-gas.ipynb](ether-transfers-tx-base-value-gas.ipynb)
analyses the runtime of `test_ether_transfers_onchain_receivers` from the EIP-7904
benchmark run and derives proposed new gas values for `TX_BASE` (per-tx base, currently
21 000) and `VALUE_GAS` (extra gas for non-zero value transfers, currently 9 000) — the
two parameters EIP-2780 targets. It fits an NNLS model per `(client, case_id)`, converts
the coefficients to gas at a 100 Mgas/s anchor, and surfaces the worst-case driver per
parameter.

Today this lives only as a notebook that imports analysis code from the sibling
`evm-gas-repricings` repo via a hard-coded `../src` path and reads CSVs from a local
`reports/` tree that isn't in this repo. The goal is a **self-contained, reproducible,
static dashboard deployed to GitHub Pages** that: (1) pulls benchmark data with
`benchmarkoor-fetch`, (2) ports the analysis functions in-repo, (3) renders the notebook's
analysis as **interactive plots and tables** plus **static background sections**.

This plan mirrors the locked-in house pattern in
`/Users/maria/Documents/ef/eip-7904-repricing/.claude/implementation_plan.md` (static
multi-page Jinja2 + vanilla-JS site, committed data, Makefile pipeline, GitHub Pages from
`/site` on `main`, token in a gitignored `secrets.json`). Departures from that blueprint,
all driven by this task:

1. **Port `evm-gas-repricings/src` functions directly** instead of calling the
   `evm-gasfit` CLI — the notebook uses `fit_NNLS_without_low_diff_runs` and
   `prepare_non_simple_model_data` from `evm-gas-repricings`, not the gasfit presets.
2. **Interactive Plotly.js charts** instead of the 7904 plan's static matplotlib PNGs —
   the user explicitly asked for interactivity.
3. **A single dashboard page (+ methodology)** instead of 7904's five pages. 2780 covers
   one test and two parameters; its whole output is a worst-case summary, a ~40-row
   `new_gas` table, a ~20-row `results` table, and a few charts — one screen, not four
   pages. This keeps the template/nav/filtering surface minimal.

Decisions confirmed with the user: frontend = the 7904 house stack (Jinja2 + vanilla JS,
enhanced with Plotly.js); data pipeline = **local build, commit artifacts** (no CI fetch);
data window = **configurable via a config file**.

## Repo layout

```
eip-2780-repricing/
├── LICENSE                      # existing
├── README.md                    # intro + how-to-run + how-to-reproduce
├── pyproject.toml               # deps: numpy, pandas, scipy, pyarrow, jinja2, pyyaml; editable benchmarkoor-fetch
├── .gitignore                   # __pycache__/, .cache/, secrets.json, data/raw/*.parquet
├── secrets.json                 # GITIGNORED — {"BENCHMARKOOR_TOKEN": "bmk_..."}
├── Makefile                     # THE orchestrator: fetch → analyze → site
├── configs/
│   └── benchmarkoor.yaml        # fork/network/test_type + start_date/end_date window
├── scripts/
│   ├── analysis.py              # ported NNLS core + notebook reproduction → data/results.json
│   └── build_site.py            # results.json + site_src/ → site/
├── data/
│   ├── raw/                     # bench_data.parquet, trace.parquet, meta.json (gitignored)
│   └── results.json             # THE committed artifact (auditable, diffable)
├── site_src/
│   ├── templates/
│   │   ├── base.html            # shared header/footer (+ Plotly.js CDN include)
│   │   ├── index.html           # the dashboard: summary → proposal table → charts → detail tables
│   │   └── methodology.html     # static background sections
│   └── assets/
│       ├── style.css
│       └── charts.js            # ~3 inline Plotly calls reading window.DASHBOARD_DATA
└── site/                        # SERVED by GitHub Pages from /site on main
    ├── index.html  methodology.html
    ├── style.css  charts.js
    └── data.js                  # window.DASHBOARD_DATA = { ... }  (embedded at build time)
```

Flat `scripts/` (no package, no `__init__.py`, no `-m` entrypoints) and a single committed
data artifact, mirroring 7904's `scripts/build_site.py`.

## Step 1 — Port the analysis functions into `scripts/analysis.py`

Fold all four ported pieces into the top of `analysis.py` (they depend only on **numpy,
pandas, scipy** — no statsmodels; `NNLSResults` mimics that interface). The two tiny
helpers don't merit their own modules.

| Function / class | Source | Notes |
| --- | --- | --- |
| `extract_param_values` | `evm-gas-repricings/src/data.py:28-36` | 8 lines. Copy the function only; do **not** bring `data.py`'s benchmarkoor/sqlalchemy/requests helpers. |
| `prepare_non_simple_model_data` | `evm-gas-repricings/src/runtime_estimation.py:88-112` | ~25 lines. Builds design matrix `["opcount"] + active params`, multiplying each extra param by `opcount`. Calls `extract_param_values`. |
| `fit_NNLS`, `fit_NNLS_without_low_diff_runs`, `find_low_diff_runs` | `evm-gas-repricings/src/nnls.py:14-192` | `scipy.optimize.nnls` + `scipy.stats.zscore`. `find_low_diff_runs` needs columns `test_file, test_name, test_params, ingestion_timestamp, opcount, run_duration_ms`. Required for parity (filters only when R²≤0.5). |
| `NNLSResults` | `evm-gas-repricings/src/nnls_results.py` | Self-contained class (249 lines). Copy whole. Provides `params`, `pvalues`, `rsquared`, `rsquared_adj`, `nobs`, `conf_int()`, `summary()`. |

The new-gas conversion is a one-liner from `proposal.py:228-235` — reproduce inline:
`new_gas = ceil(anchor_rate * runtime_ms / 1e3)` (same for conf-int low/high).

## Step 2 — Configurable data fetch (`benchmarkoor-fetch`)

`configs/benchmarkoor.yaml` **pins the suite hash** for reproducibility (mirrors the 7904
plan's `suites` approach, which is more stable than a date range):

```yaml
query:
  fork: amsterdam
  suites:
    - a11611f320a39015   # jochennet stateful (the run the notebook analysed)
http: { page_size: 10000, max_workers: 5 }
output: { estimator_inputs: true, merged_parquet: true, trace_parquet: true }  # trace needed for JUMP-based opcount
cache: { enabled: true }
```

`network`/`test_type`/`start_date` are omitted because the run is identified by the pinned
**suite hash** instead (`benchmarkoor-fetch suites --network <n> --fork <f> --test-type <t>`
re-resolves the latest matching hash if it ever needs re-pinning).

`trace_parquet: true` is **required** — the notebook's opcount derivation depends on the
per-opcode `JUMP` column (see Step 3).

**No fetch wrapper script.** `benchmarkoor-fetch` is already a CLI, and the Makefile pulls
the token from `secrets.json` with `jq` and exports it (Step 4). So `make fetch` invokes
`benchmarkoor-fetch run --config configs/benchmarkoor.yaml --out data/raw/` directly —
exactly like the 7904 plan. Outputs `bench_data.parquet`, `trace.parquet`, `meta.json`
(per `benchmarkoor-fetch/result.py`).

**Column-mapping note:** `benchmarkoor-fetch` emits `test_runtime_ms`, whereas the ported
NNLS code expects `run_duration_ms`. `analysis.py` must rename `test_runtime_ms →
run_duration_ms`. Available columns: `run_id, client_name, test_title, test_file,
test_name, test_opcode, test_params, test_runtime_ms, ingestion_timestamp,
block_limit_million, opcount`.

## Step 3 — Analysis (`scripts/analysis.py`, run via `make analyze`)

After the ported core, faithfully reproduce the notebook (cells 4–20), reading parquet
instead of CSV:

1. **Load & filter** `bench_data.parquet` to `test_name == "test_ether_transfers_onchain_receivers"`; load `trace.parquet` (`test_title`, `JUMP`). Rename `test_runtime_ms → run_duration_ms`.
2. **Derive `transfer_amount` and `case_id`** from `test_params` (regex `case_id_(.+)$`, `extract_param_values(..., "transfer_amount")`).
3. **Derive `opcount`** with the notebook's "opcode trick" (cell 4) — this is the **source of truth**; ignore `benchmarkoor-fetch`'s own `opcount` column entirely and recompute. Merge `trace.parquet`'s `JUMP` on `test_title`, then: contract-target cases emit one `JUMP` per tx → `opcount = JUMP`; EOA cases have no trace opcodes (`JUMP` is NaN) → `opcount = floor(block_limit_million * 1e6 / 21000)`. i.e. `opcount = JUMP.where(JUMP.notna(), floor(block_limit_million * 1e6 / 21000))`.
4. **Fit per `(client, case_id)`**: drop `transfer_amount`, call `prepare_non_simple_model_data(fit_df, ["transfer_amount"])`, then `fit_NNLS_without_low_diff_runs`. Collect `results_df` (nobs, rsquared(_adj), intercept, slope + CI + pvalue, transfer_amount coef + CI + pvalue).
5. **Convert to gas** at `ANCHOR_RATE = 1e8`: slope→`TX_BASE`, transfer_amount→`VALUE_GAS`; `new_gas`, `new_gas_rounded`, conf-int low/high (all `ceil`), `current_gas` (21 000 / 9 000), `change`.
6. **Worst-case selection**: per-`case_id` and overall `idxmax` on `new_gas_rounded` per param; plus poor-fit (R²≤0.5) caveats.

`analysis.py`'s `__main__` serialises everything to **`data/results.json`** (NaN→null) —
the single committed artifact. No parallel CSVs; the JSON is the auditable record and the
site's data source. Keep the cell-20 **summary as computed values, not pre-rendered
prose** — emit `worst_tx_base`, its driver client/case/R²/pvalue, the percent change, and
the over/under-priced direction; the template assembles the sentence (Step 4).

`results.json` schema (consumed by the frontend):

```jsonc
{
  "meta": { "anchor_rate": 1e8, "test_name": "...", "window": {...}, "generated_from": "<meta.json>", "clients": [...], "cases": [...] },
  "results": [ { "client_name", "case_id", "nobs", "rsquared", "rsquared_adj", "slope", "slope_conf_int_low/high", "slope_pvalue", "transfer_amount", "transfer_amount_conf_int_low/high", ... } ],
  "new_gas": [ { "client_name", "case_id", "param", "runtime_ms", "new_gas_rounded", "new_gas_conf_int_low/high", "current_gas", "change", "rsquared", "pvalue" } ],
  "worst_case_overall": [ {param, client_name, case_id, new_gas_rounded, new_gas_conf_int_low/high, rsquared, pvalue, current_gas, change} ],
  "worst_case_by_case": [ ... ],
  "summary": {
    "tx_base":   { "new_gas", "client_name", "case_id", "rsquared", "pvalue", "current_gas", "change_pct", "direction" },
    "value_gas": { "new_gas", "client_name", "case_id", "rsquared", "pvalue", "current_gas", "change_pct", "direction" },
    "caveats": [ { "param", "client_name", "case_id", "rsquared" } ]
  }
}
```

## Step 4 — Static site (`scripts/build_site.py` + `site_src/`, run via `make site`)

Mirror the 7904 builder: load `results.json`, set up Jinja2, render each template to
`site/`, copy `site_src/assets/` into `site/`. **Key difference:** instead of copying PNGs,
emit `site/data.js` containing `window.DASHBOARD_DATA = <results.json>;` so the page is
fully self-contained (no `fetch()` — avoids project-pages base-path issues, consistent with
the 7904 "no JSON fetch" stance). `base.html` includes Plotly.js via CDN. **No table
library** — tables are 20–40 rows, rendered as plain build-time HTML with worst-case cells
highlighted (no DataTables/grid.js, no jQuery, no `tables.js`).

**Pages** (both extend `base.html` → shared header, two-link nav, reproducibility footer
with window + `benchmarkoor-fetch` version + commit hash from `meta.json`):

1. **`index.html` — Dashboard.** Everything the notebook surfaces, top to bottom:
   - **Headline summary** — the `summary` block assembled into prose by the template
     (worst-case TX_BASE / VALUE_GAS, drivers, % change vs current, over/under-priced
     takeaway, R² caveats).
   - **Worst-case proposal table** — one row per param: proposed, current, change.
   - **Charts** (interactive Plotly): grouped **bar charts with CI error bars** per param
     (`TX_BASE`, `VALUE_GAS`) vs. the current-value reference line (notebook cell 18 — the
     richer of cell 17/18; the redundant heatmap is dropped); one combined **model-fit
     diagnostics** chart (R² per (client, case), cell 10) since slope/coef CI also live as
     table columns.
   - **Detail tables** — the full `new_gas` table (worst-case cells highlighted) and the
     `results` table (R², slope + CI, transfer_amount coef + CI). Plain static HTML.
2. **`methodology.html` — Background** (static narrative): EIP-2780 background, the four
   `case_id`s (contract / unique-code-jumpdest / existent / nonexistent EOA), the temporary
   "opcode trick" for `opcount`, the NNLS model + bootstrap inference + low-diff-run
   filtering, the 100 Mgas/s anchor and worst-case selection, and end-to-end
   reproducibility instructions.

`charts.js` holds ~3 inline `Plotly.newPlot` calls reading `window.DASHBOARD_DATA` — no
generic builder abstraction; the data is small and the chart set is fixed.

## Step 5 — Orchestration & deployment

The **`Makefile` is the only orchestrator** (mirrors 7904): it reads the token via `jq`
from `secrets.json`, exports it, and each target is one command.

```makefile
BENCHMARKOOR_TOKEN := $(shell jq -r .BENCHMARKOOR_TOKEN secrets.json)
export BENCHMARKOOR_TOKEN

all: fetch analyze site
fetch:   ; benchmarkoor-fetch run --config configs/benchmarkoor.yaml --out data/raw/
analyze: ; python scripts/analysis.py       # data/raw/ → data/results.json
site:    ; python scripts/build_site.py      # data/results.json + site_src/ → site/
clean:   ; rm -rf data/ site/
```

Typical use: one-time `secrets.json`, then `make` (or a single step while iterating).

`pyproject.toml`: depend on `numpy, pandas, scipy, pyarrow, jinja2, pyyaml`, plus an
editable/path dep on local `benchmarkoor-fetch`. **Deployment:** GitHub Pages → `main`
branch, `/site` folder, **no CI** (local build, commit `site/` + `data/results.json`,
push). `secrets.json` and `data/raw/*.parquet` are gitignored; commit `data/results.json`
so the site is reproducible/auditable. README documents requesting a Benchmarkoor token and
the `make` workflow.

## Verification

1. **Ported functions** — unit-smoke each against a tiny synthetic DataFrame:
   `fit_NNLS` recovers a known slope; `prepare_non_simple_model_data` returns
   `["opcount", "transfer_amount"]` and multiplies the param by opcount;
   `extract_param_values("...case_id_x-transfer_amount_1", "transfer_amount") == "1"`.
2. **Pipeline parity** — run `make fetch && make analyze`; confirm `results.json`'s
   `worst_case_overall` reproduces the notebook's headline numbers (TX_BASE worst-case
   ≈ besu/`diff_to_nonexistent`; VALUE_GAS worst-case ≈ besu/`diff_to_existent`) and that
   `results` row count/clients match the notebook's `results_df`. Spot-check a few
   `new_gas_rounded` values (e.g. geth `diff_to_contract` TX_BASE ≈ 10 454).
3. **Site** — `make site`, then serve locally (`python -m http.server` in `site/`); verify
   both pages render, Plotly charts are interactive (hover/zoom), the proposal/detail
   tables render with worst-case cells highlighted, the headline summary reads correctly,
   and the reproducibility footer is populated.
4. **Pages readiness** — confirm relative asset paths work under a project-pages base path
   (`/eip-2780-repricing/…`) by loading the locally served `/site` from a subpath.

## Open items

Both original open items are now resolved:

- **Benchmarkoor suite — resolved (pinned).** `configs/benchmarkoor.yaml` pins suite
  `a11611f320a39015` (jochennet stateful), the run the notebook analysed — no date range.
- **`opcount` — resolved (JUMP/floor trick).** `benchmarkoor-fetch`'s `opcount` column is
  ignored; `analysis.py` recomputes `opcount` from the trace `JUMP` count with the
  `floor(block_gas_limit / 21000)` EOA fallback (Step 3.3). Notebook logic is the source of
  truth.

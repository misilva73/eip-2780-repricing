# EIP-2780 Repricing Dashboard

Derives proposed gas values for EIP-2780 by measuring the end-to-end cost of each
transfer kind directly: `ZERO_VALUE_TRANSFER` (plain transfer, referenced against
21000) and `VALUE_TRANSFER` (value transfer, also referenced against 21000) — plus
the derived `TX_VALUE_COST` (`VALUE_TRANSFER − ZERO_VALUE_TRANSFER`, the marginal
cost of moving value, referenced against 9000). For each `(client, case_id)` it
fits **two independent NNLS models** — one on the `transfer_amount=0` runs, one on
the `transfer_amount=1` runs, each `[const, opcount]` — converts the opcount slopes
to gas at a fixed throughput anchor (`ANCHOR_RATE`, currently 100 Mgas/s), picks the
worst case per param, and renders a static
GitHub Pages dashboard.

## Pipeline

`make` runs `fetch → analyze → site` (see [Makefile](Makefile)):

- `make fetch`   — `benchmarkoor-fetch` → `data/raw/*.parquet` + `meta.json` (gitignored)
- `make analyze` — [scripts/analysis.py](scripts/analysis.py) → `data/results.json` (latest, committed) **and** archives a copy to `data/runs/<run_id>.json` (committed history)
- `make site`    — [scripts/build_site.py](scripts/build_site.py): `data/runs/*` + `site_src/` → `docs/` (three pages per run — a dashboard, latest at `index.html`; its sibling proposed-gas detail page, latest at `detail.html`; and its sibling model-fit detail page, latest at `model-fit.html`) plus two run-agnostic singletons, `docs/methodology.html` and `docs/trends.html`

## Run history

The dashboard shows the latest run with a run selector (a banner above the hero)
to switch to previous runs. History accumulates going forward — there is no backfill.

- Each `make analyze` archives its result to `data/runs/<run_id>.json` (committed).
  `run_id` is `meta.run_id`, keyed on the data-window end + suite, so
  re-analyzing the same data **overwrites in place** instead of duplicating.
  `data/results.json` remains the canonical latest pointer (a copy of the newest run).
- `make site` renders one self-contained dashboard page per archived run: latest →
  `docs/index.html` + `docs/data.js`; each older run → `docs/run-<id>.html` +
  `docs/data-<id>.js`. Each run also gets two sibling pages, both tables that used
  to live on the dashboard, moved off onto their own pages and linked from the nav
  ("Detail" and "Model Fit", between "Dashboard" and "Trends"):
  - **Detail page** — the full proposed-gas detail table: latest → `docs/detail.html`,
    each older run → `docs/detail-<id>.html`.
  - **Model Fit page** — the full NNLS model-fit table: latest →
    `docs/model-fit.html`, each older run → `docs/model-fit-<id>.html`.

  Neither needs a `data-*.js` — both tables are server-rendered (from `new_gas` and
  `results` respectively), not read from `window.DASHBOARD_DATA` — and each has its
  own run selector (`build_run_index` in [build_site.py](scripts/build_site.py) is
  shared by all three page families, just parameterized on basename/prefix) that
  switches between pages of that same family, not the dashboard. All three
  selectors are a custom button+listbox (server-rendered in
  [index.html](site_src/templates/index.html) /
  [detail.html](site_src/templates/detail.html) /
  [model-fit.html](site_src/templates/model-fit.html); each option is a plain link,
  so switching runs is just navigation between these pages). `charts.js`
  (`initRunDropdown`) only adds open/close + keyboard handling — not a native
  `<select>`, so the open list matches the page font. With a single archived run
  it degrades to a static label. Stale `run-*.html` / `detail-*.html` /
  `model-fit-*.html` / `data-*.js` are cleared at the start of each build.
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
  `collect_trends` also groups consecutive runs by `meta.anchor_rate` into
  `anchor_eras`; with more than one era [trends.html](site_src/templates/trends.html)
  renders a **mixed-anchor caveat** above the filters (gas is runtime × anchor, so an
  anchor change puts a step in every gas series and in the since-last-run delta —
  runtime series are unaffected). Archived runs keep the anchor they were analyzed
  under and are **never rescaled**; the raw parquet for old windows is gone, so they
  can't be re-analyzed either. The note disappears on its own once every archived run
  shares one anchor.

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
  `detail.html` / `detail-<id>.html`, `model-fit.html` / `model-fit-<id>.html`,
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
- **`opcount` is recomputed**, ignoring benchmarkoor's own column: one per-tx
  marker opcode from the trace for contract/delegated cases (`JUMP` for jumping
  contracts, else `STOP` for STOP-only contracts — minimal / `*_max` / delegated),
  else — for the marker-less EOA cases — `floor(block_gas_limit / per_tx_gas)`
  where `per_tx_gas` is the tx's **EIP-2780** cost (`EOA_TX_GAS`: self 12000,
  zero-value 15000, value-to-EOA 21000, value-to-new-account 183600), **not** a
  flat 21000. These blocks are packed under EIP-2780 pricing, so a flat base would
  mis-count the cheaper/dearer EOA cases and mis-scale their gas.
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
  proper statistical error propagation — the two independent fits' own CI margins
  combine in quadrature (`sqrt(a² + b²)`), not by interval arithmetic, which sums
  the two margins and overstates the diff's uncertainty) references
  `VALUE_GAS_CURRENT` (9000). Note `VALUE_TRANSFER` is now fit directly (the
  value-subset opcount slope), not summed as `TX_BASE + VALUE_GAS`.
  `build_site.py`'s `fix_tx_value_cost_ci` re-derives `TX_VALUE_COST`'s CI (not its
  point value) the same way from each run's own `ZERO_VALUE_TRANSFER` /
  `VALUE_TRANSFER` rows, so already-archived runs get the corrected CI too even
  though their raw parquet (and so re-analysis) is gone.
- **The Summary section is one table: goal targets per client**
  (`collect_goals` in [build_site.py](scripts/build_site.py), modelled on the
  eip-8038 Goals page). **One row per `GOAL_SPECS` entry** — five goals, each a sum
  of EIP-2780's own components (`TX_BASE_COST` 12000, `COLD_ACCOUNT_ACCESS` 3000,
  `TX_VALUE_COST` 6000) that has to cover one param over a set of receiver cases.
  A spec names its cases by *shape* (`goal_variant`: `self` / `delegated` /
  `standard`) and its parameters in `params`, and `GOAL_SPECS` order is the row
  order:

  | Goal (`name`) | `formula` | Target | `params` | Shapes covered |
  | --- | --- | --- | --- | --- |
  | Transfer to self | `TX_BASE_COST` | 12000 | `ZERO_VALUE_TRANSFER` + `VALUE_TRANSFER` | self |
  | No-value transfer | `+ COLD_ACCOUNT_ACCESS` | 15000 | `ZERO_VALUE_TRANSFER` | standard |
  | Transfer | `+ COLD_ACCOUNT_ACCESS + TX_VALUE_COST` | 21000 | `VALUE_TRANSFER` | standard |
  | No-value transfer to delegated account | `+ 2 × COLD_ACCOUNT_ACCESS` | 18000 | `ZERO_VALUE_TRANSFER` | delegated |
  | Transfer to delegated account | `+ 2 × COLD_ACCOUNT_ACCESS + TX_VALUE_COST` | 24000 | `VALUE_TRANSFER` | delegated |

  The Goal column renders the short `name`; the component sum (`formula`) is the
  cell's tooltip, so the column stays narrow. The "Cases covered" column is
  likewise abbreviated by `format_goal_cases`: two or more contract receivers read
  as one "Contracts" (a lone one keeps its own label), with the unabbreviated list
  as the cell's tooltip.

  Columns are clients; each cell is that client's **worst (highest)**
  `new_gas_rounded` across the goal's cases **and params** — the budget has to cover
  all of them —
  tinted green at or under the goal, amber up to `GOAL_MID_MARGIN` (25%) over, red
  beyond, `—` where the client has no fit for any of them. The tooltip names the
  case the worst value came from (and its param, on the one multi-param goal). Note
  a **self-transfer is 12000 whether or not it moves value** — moving value to
  yourself touches no second account — so `diff_to_self` sits only in the
  "Transfer to self" row, which covers both params, and is *not* one of the
  "Transfer" goal's cases. `TX_VALUE_COST` gets no row — it is a component of the goals,
  not a target. A goal no client has data for is dropped, so older runs (which
  predate the self/delegated cases) render two rows, not five. These are targets,
  independent of `current_gas`/`analysis.py`; nothing is read from the run's
  `summary` block except the caveats.
- **Excluded cases are a render-time filter, not an analysis one.** Two sets in
  [build_site.py](scripts/build_site.py), deliberately different:
  `EXCLUDED_CASES` = `{diff_to_unique_code_jumpdest_contract, diff_to_contract}`
  drops those `case_id`s from the dashboard's bar charts, its Summary section
  (the goal-targets table) and the Detail page's
  worst-case highlight; `TRENDS_EXCLUDED_CASES` = `{diff_to_contract}` drops
  only that one from the Trends page, which **still charts the jumpdest case**.
  `analysis.py` fits every case regardless and both detail tables (the Detail
  page's proposed-gas table and the Model Fit page's NNLS table) list every row.
  `diff_to_contract`'s drop from `EXCLUDED_CASES` is **conditional per run**, via
  `excluded_cases_for()`: it's only actually excluded once a run also has the
  three size/uniqueness contract variants (`diff_to_contract_minimal`,
  `_same_max`, `_diff_max` — added in suite `0d93b5bf3b970403`), since those make
  the plain case redundant. Runs from suite `d88b18464da7445e` and earlier predate
  those variants, so `diff_to_contract` is their only contract-shaped case and
  stays charted there. `TRENDS_EXCLUDED_CASES` is **not** conditional — it drops
  `diff_to_contract` from every run's Trends series regardless. Consequences:
  - The dashboard's `summary` / `worst_case_overall` are **re-derived in
    `build_site.py`** (`rebuild_worst_cases`, `rebuild_summary`) from the
    non-excluded `new_gas` rows, not read from the run JSON; templates get the
    filtered rows as `summary_new_gas`. `rebuild_summary` now only feeds the R²/
    p-value caveat blocks — the Summary's headline is the goal-targets table below.
  - `collect_goals` is fed the same filtered rows, so the goal table covers exactly
    the cases the charts show.
  - `collect_trends` filters its rows with `TRENDS_EXCLUDED_CASES` and re-derives
    its `binding` series from them (not from the run's stored `worst_case_overall`,
    which ranks over every case), so trends.js needs no filter of its own.
  - `charts.js` has no hardcoded copy of `EXCLUDED_CASES` — each run's data file
    embeds that run's resolved `excluded_cases_for()` result as
    `DASHBOARD_DATA.excluded_cases`, and `charted()` filters against that.
  - The dashboard's **"Jumpdest cost"** section (below Charts) is specifically
    *about* the excluded `diff_to_unique_code_jumpdest_contract` case: a bar chart
    of its proposed-gas diff against `diff_to_contract_diff_max` (the case it's
    otherwise closest to in shape), per param, no goal line. `collect_jumpdest_diff`
    in build_site.py reads the **raw** (unfiltered) `new_gas`, since its one case is
    excluded from `charted`, and propagates the diff's CI the same way
    `TX_VALUE_COST` does (margins combine in quadrature) — but leaves it unclamped,
    since the sign is the point (does the extra `JUMP` cost more or less). Rendered
    by `plotJumpdestDiff` in charts.js; has its own repeated client legend
    (`#jumpdest-legend`, via `buildChartsLegend(hostId)`) since the section sits far
    enough below the Charts section's shared one to need a nearby copy.
  Because nothing is baked into the data, the exclusions apply to **every archived
  run page**, and emptying the sets + `make site` fully reverts them. Verified: on
  runs where no excluded case was binding, the rebuilt summary is byte-identical to
  analysis.py's.
- **Each dashboard page's data file embeds its run verbatim** as
  `window.DASHBOARD_DATA` — no runtime `fetch()` (avoids project-pages base-path
  issues). `index.html` loads `data.js`; `run-<id>.html` loads `data-<id>.js`.
  `charts.js` reads whichever is loaded. The Detail and Model Fit pages have no
  data file: their tables are rendered server-side from `new_gas` / `results` at
  build time, and their only script is `charts.js` (for the run selector, table
  filters and tooltips — none of which need `window.DASHBOARD_DATA`). All output
  is flat under `docs/` so the dropdowns' relative links work.

## Deploy

GitHub Pages serves `/docs` on `main`. No CI. After a data/site change, commit
`data/results.json`, the new/changed `data/runs/*.json`, and `docs/`, then push.

**Never create a new git branch unless explicitly asked.** Commit directly to
`main` (the deploy branch) — do not branch first.

## Verify before commit

`make site && (cd docs && python -m http.server)` — check the Dashboard, Detail,
Model Fit, Methodology, and Trends pages render, Plotly charts are interactive
(Dashboard only — Detail and Model Fit have none), tables show worst-case
highlights, footer populated (incl. `generated`), and the nav's "Detail" / "Model
Fit" links land on the right table. With >1 archived run, each of the Dashboard's,
Detail's and Model Fit's own **Viewing run** selector banners switches pages and
the latest reads "(latest)" (switching run on one page family doesn't jump you to
the others), and the Trends page's since-last-run delta table + Δ% bar populate
(with one run it shows a "only one run archived" note). On the latest run the
Summary's goal table should show five rows (targets 12,000 / 15,000 / 21,000 /
18,000 / 24,000, in that order) with a green/amber/red cell per client; hovering a
cell shows its margin and which case the worst value came from. Per the
excluded-cases invariant above: no dashboard chart or Summary table row should
mention `Contract (jumpdest)` or `Contract`, the Trends page should still show
`Contract (jumpdest)` but not `Contract`, and both detail tables (Detail page +
Model Fit page) should list every case. The worst case (the highlighted rows on
the Detail page) on the latest run currently reads erigon /
`diff_to_contract_diff_max` for `ZERO_VALUE_TRANSFER` and erigon /
`diff_to_nonexistent` for `VALUE_TRANSFER` and `TX_VALUE_COST` (this follows the
data — re-check after a data refresh).

# EIP-2780 Repricing Dashboard

Analyses the runtime of `test_ether_transfers_onchain_receivers` from the EIP-7904
benchmark run to derive proposed new gas values for EIP-2780's `TX_BASE` (currently
21000) and `VALUE_GAS` (currently 9000) parameters. It fits an NNLS model per
`(client, case_id)`, converts the coefficients to gas at a 100 Mgas/s anchor, surfaces
the worst-case driver per parameter, and renders the whole analysis as an interactive
static dashboard for GitHub Pages. Each run is archived, and the dashboard has a run
selector to view previous runs alongside the latest.

## Requirements

- Python 3.11+
- `make`
- `jq`
- A Benchmarkoor API token

## Setup

1. Request a Benchmarkoor API token.
2. Create `secrets.json` at the repo root (it is gitignored):

   ```json
   {"BENCHMARKOOR_TOKEN": "bmk_..."}
   ```

## Usage

Run the full pipeline (fetch → analyze → site):

```sh
make
```

Or run the targets individually:

```sh
make fetch     # pull benchmark data into data/raw/
make analyze   # build data/results.json + archive a copy to data/runs/<run_id>.json
make site      # render every archived run into docs/ (latest = index.html)
```

Serve the built site locally:

```sh
cd docs && python -m http.server
```

Each `make analyze` archives its result to `data/runs/<run_id>.json` (committed), so
the dashboard accumulates a history of runs. To remove a run from the dashboard:

```sh
make clean-run RUN_ID=<run_id>   # delete an archived run and re-render
```

## Repo layout

```
eip-2780-repricing/
├── Makefile              # orchestrator: fetch → analyze → site
├── pyproject.toml
├── configs/
│   └── benchmarkoor.yaml # pinned suite / fetch config
├── scripts/
│   ├── analysis.py       # ported NNLS analysis → data/results.json (+ data/runs/)
│   ├── build_site.py     # data/runs/ + site_src/ → docs/
│   └── clean_run.py      # delete an archived run (make clean-run)
├── data/
│   ├── raw/              # fetched parquet/json (gitignored)
│   ├── results.json      # committed latest-run artifact
│   └── runs/             # committed per-run history (one file per run_id)
├── site_src/
│   ├── templates/        # Jinja2 templates
│   └── assets/           # style.css, charts.js
└── docs/                 # built site served by GitHub Pages (index.html + run-<id>.html)
```

## Deployment

GitHub Pages serves from the `/docs` folder on `main`. There is no CI — build locally,
then commit `docs/`, `data/results.json`, and the new/changed `data/runs/*.json`, and push.

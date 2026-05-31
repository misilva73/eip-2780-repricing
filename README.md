# EIP-2780 Repricing Dashboard

Analyses the runtime of `test_ether_transfers_onchain_receivers` from the EIP-7904
benchmark run to derive proposed new gas values for EIP-2780's `TX_BASE` (currently
21000) and `VALUE_GAS` (currently 9000) parameters. It fits an NNLS model per
`(client, case_id)`, converts the coefficients to gas at a 100 Mgas/s anchor, surfaces
the worst-case driver per parameter, and renders the whole analysis as an interactive
static dashboard for GitHub Pages.

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
make analyze   # build data/results.json
make site      # render data/results.json + site_src/ into docs/
```

Serve the built site locally:

```sh
cd docs && python -m http.server
```

## Repo layout

```
eip-2780-repricing/
├── Makefile              # orchestrator: fetch → analyze → site
├── pyproject.toml
├── configs/
│   └── benchmarkoor.yaml # pinned suite / fetch config
├── scripts/
│   ├── analysis.py       # ported NNLS analysis → data/results.json
│   └── build_site.py     # results.json + site_src/ → docs/
├── data/
│   ├── raw/              # fetched parquet/json (gitignored)
│   └── results.json      # committed analysis artifact
├── site_src/
│   ├── templates/        # Jinja2 templates
│   └── assets/           # style.css, charts.js
└── docs/                 # built site served by GitHub Pages
```

## Deployment

GitHub Pages serves from the `/docs` folder on `main`. There is no CI — build locally,
then commit `docs/` and `data/results.json` and push.

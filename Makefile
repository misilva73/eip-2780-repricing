BENCHMARKOOR_TOKEN := $(shell jq -r .BENCHMARKOOR_TOKEN secrets.json)
export BENCHMARKOOR_TOKEN

.PHONY: all fetch analyze site serve clean clean-run

all: fetch analyze site

fetch:
	benchmarkoor-fetch run --config configs/benchmarkoor.yaml --out data/raw/

analyze:
	python scripts/analysis.py

site:
	python scripts/build_site.py

serve: site
	cd docs && python -m http.server

# Delete one archived run from data/runs/ and re-render. If it was the latest,
# the next-newest run is promoted to data/results.json. Usage:
#   make clean-run RUN_ID=2026-05-31T090116Z_a11611f320a39015
clean-run:
	@test -n "$(RUN_ID)" || { echo "usage: make clean-run RUN_ID=<id>"; exit 2; }
	python scripts/clean_run.py "$(RUN_ID)"

clean:
	rm -rf data/raw/*.parquet data/raw/*.json data/results.json docs/*.html docs/*.css docs/*.js

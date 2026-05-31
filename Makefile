BENCHMARKOOR_TOKEN := $(shell jq -r .BENCHMARKOOR_TOKEN secrets.json)
export BENCHMARKOOR_TOKEN

.PHONY: all fetch analyze site serve clean

all: fetch analyze site

fetch:
	benchmarkoor-fetch run --config configs/benchmarkoor.yaml --out data/raw/

analyze:
	python scripts/analysis.py

site:
	python scripts/build_site.py

serve: site
	cd docs && python -m http.server

clean:
	rm -rf data/raw/*.parquet data/raw/*.json data/results.json docs/*.html docs/*.css docs/*.js

PYTHON ?= python3
INPUT ?= examples/video_summary.json
OUTPUT ?= /tmp/edit_suggestions.json

.PHONY: lint test run_sample

lint:
	PYTHONPYCACHEPREFIX=.pycache $(PYTHON) -m compileall -q optimizer tests

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

run_sample:
	PYTHONPATH=. $(PYTHON) -m optimizer.cli --input $(INPUT) --output $(OUTPUT)
	@echo "Wrote $(OUTPUT)"

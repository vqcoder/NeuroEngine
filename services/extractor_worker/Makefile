PYTHON ?= python3
SAMPLE_DIR ?= /tmp/biotrace_sample_session
SAMPLE_OUT ?= /tmp/biotrace_sample_output.jsonl

.PHONY: lint test run_sample

lint:
	@if $(PYTHON) -m ruff --version >/dev/null 2>&1; then \
		$(PYTHON) -m ruff check biotrace_extractor biotrace_extractor_tests; \
	else \
		PYTHONPYCACHEPREFIX=.pycache $(PYTHON) -m compileall -q biotrace_extractor; \
		echo "ruff not installed; ran compileall as a syntax lint fallback."; \
	fi

test:
	PYTHONPATH=. $(PYTHON) -m unittest discover -s biotrace_extractor_tests -p "test_*.py" -v

run_sample:
	$(PYTHON) scripts/create_sample_session.py --output-dir $(SAMPLE_DIR)
	$(PYTHON) -m biotrace_extractor.cli --input $(SAMPLE_DIR) --output $(SAMPLE_OUT)
	@echo "Wrote $(SAMPLE_OUT)"

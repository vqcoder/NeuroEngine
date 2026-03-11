PYTHON ?= python3
DATASET_PATH ?= artifacts/train_dataset.csv
MODEL_PATH ?= artifacts/baseline_xgb.joblib
SEED ?= 42

.PHONY: export train run test

export:
	$(PYTHON) -m ml_pipeline.export_dataset --output $(DATASET_PATH)

train:
	$(PYTHON) -m ml_pipeline.train --dataset $(DATASET_PATH) --model-output $(MODEL_PATH) --seed $(SEED)

run:
	$(PYTHON) -m ml_pipeline.run_pipeline --dataset-path $(DATASET_PATH) --model-path $(MODEL_PATH) --seed $(SEED)

test:
	$(PYTHON) -m pytest -q

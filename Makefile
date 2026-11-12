# Git-Bash / Linux / macOS.  Windows PowerShell: .\run_pipeline.ps1
PY ?= python
export PYTHONPATH := src

.PHONY: data db pipeline reuse notebooks powerbi test all clean

data:      ## download the Olist dataset (public Kaggle endpoint, no API key needed)
	mkdir -p 02_data/raw && curl -L -o 02_data/raw/olist.zip https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce && cd 02_data/raw && unzip -o olist.zip && rm olist.zip
db:        ## PostgreSQL 16 on localhost:5435
	docker compose up -d db
pipeline:  ## everything: raw -> staging -> dw -> mart -> experiments (~26 min) -> analytics -> KPI -> pbi views -> reports
	$(PY) -m custseg.pipeline
reuse:     ## same, but reuse the saved experiment grid (artifacts/segmentation_results.joblib)
	$(PY) -m custseg.pipeline --reuse-experiments
notebooks: ## build + execute the 13 PRD notebooks
	$(PY) -m custseg.notebooks
powerbi:   ## regenerate 11_powerbi/CustomerSegmentation.pbip
	$(PY) 11_powerbi/build_pbip.py
test:      ## unit tests (no database needed)
	$(PY) -m pytest -q tests
all: data db pipeline notebooks powerbi
clean:
	rm -rf artifacts/segmentation_results.joblib 02_data/processed/*.csv

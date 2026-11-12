# Windows PowerShell runner (same steps as the Makefile).
#   .\run_pipeline.ps1            -> full run (experiments ~26 min)
#   .\run_pipeline.ps1 -Reuse     -> reuse the saved experiment grid
param([switch]$Reuse)
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"
if (-not (Test-Path "02_data/raw/olist_orders_dataset.csv")) {
    New-Item -ItemType Directory -Force 02_data/raw | Out-Null
    curl.exe -L -o 02_data/raw/olist.zip https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce
    Expand-Archive -Force 02_data/raw/olist.zip 02_data/raw; Remove-Item 02_data/raw/olist.zip
}
docker compose up -d db
if ($Reuse) { python -m custseg.pipeline --reuse-experiments } else { python -m custseg.pipeline }
python -m custseg.notebooks
python 11_powerbi/build_pbip.py

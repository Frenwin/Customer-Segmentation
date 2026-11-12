# 02_data

| Folder | Content | In Git |
|---|---|---|
| `raw/` | the 9 Olist CSV files exactly as downloaded | no (126 MB) — download below |
| `external/` | reserved for enrichment data (none used) | – |
| `interim/` | scratch outputs | no |
| `processed/` | `customer_segmentation.csv` (one row per customer, final + alternative labels, CLV) | no (regenerated) |
| `dataset_manifest.json` | rows, columns, size and **SHA-256 of every source file**; `dataset_version` = hash of the hashes | yes |

## Download

Public Kaggle dataset *Brazilian E-Commerce Public Dataset by Olist* (license CC BY-NC-SA 4.0). The public download
endpoint works without an API key:

```bash
curl -L -o 02_data/raw/olist.zip https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce
cd 02_data/raw && unzip olist.zip && rm olist.zip
```

The pipeline stores the file hashes in `dataset_manifest.json`; compare `dataset_version` to make sure you are
analysing the same data version as the documented results.

## Layers in PostgreSQL (`localhost:5435`, db `custsegdb`)

`raw` (as-is TEXT) → `staging` (typed, de-duplicated, flagged) → `dw` (star schema) → `mart` (customer analytics)
→ `pbi` (views for Power BI). See `05_data_engineering/documentation/data_pipeline.md`.

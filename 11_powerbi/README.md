# Power BI — Customer Segmentation Dashboard

1. Make sure PostgreSQL runs and the pipeline has populated it: `docker compose up -d db`, `python -m custseg.pipeline`
2. Open **`11_powerbi/CustomerSegmentation.pbip`** in Power BI Desktop (a version with PBIP / TMDL / PBIR support)
3. When asked for PostgreSQL credentials: user `custseg`, password `custseg` → Connect (once)

| Folder / file | Content |
|---|---|
| `build_pbip.py` | generates the whole project (model + report) from code — edit this, not the JSON |
| `CustomerSegmentation.SemanticModel/` | TMDL: 18 DirectQuery tables, 8 single-direction relationships, 78 measures (Rupiah, culture id-ID) |
| `CustomerSegmentation.Report/` | PBIR: 6 PRD dashboards + drill-through + tooltip + appendix (175 visuals) |
| `data_model/data_model.md` | relationships and filter propagation |
| `dax_measures/measures.dax` | every DAX measure in readable form |
| `dax_measures/measure_validation.md` | DAX vs SQL validation result |
| `validate_measures.py`, `tools/run_dax.ps1` | validation against the open model (local Analysis Services via ADOMD.NET) |
| `dashboard_design/design_principles.md` | layout and colour rules |

Page-by-page description: `12_documentation/dashboard_documentation.md`.

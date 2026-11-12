"""Generate the Power BI project  11_powerbi/CustomerSegmentation.pbip  — "dashboard as code".

* Semantic model : TMDL, star schema in DirectQuery on PostgreSQL schema `pbi` (05_.../02_powerbi_views.sql),
                   single-direction relationships, reusable DAX measures consistent with the analytical layer
* Report         : PBIR (public JSON schemas) - the 6 dashboards of PRD section 9 + drill-through customer
                   details + a segment tooltip page + an appendix (model comparison & KPI dictionary)
* Design         : navy header band, white cards on a cool-grey canvas, one fixed colour per segment
                   (same as the matplotlib figures), status colours only where a value has a meaning

    python 11_powerbi/build_pbip.py      # needs the PostgreSQL container (column types are read from the views)

Then open 11_powerbi/CustomerSegmentation.pbip in Power BI Desktop (credentials: custseg / custseg).
"""
from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from custseg import config, db  # noqa: E402

NAME = "CustomerSegmentation"
OUT = ROOT / "11_powerbi"
SM = OUT / f"{NAME}.SemanticModel"
RP = OUT / f"{NAME}.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
V_VISUAL, V_PAGE, V_REPORT = "2.4.0", "2.0.0", "3.0.0"
PBI_THEMES = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin\WebView2Resources\minerva\sharedresources\BaseThemes")
BASE_THEME = "Fluent2-CY26SU10"
W, H, M, G = 1280, 800, 20, 12
HEADER_H = 64
SLICER_H = 60

# ---------------------------------------------------------------------------------------------- palette
# "Charcoal & Coral" theme. Every data colour was checked for lightness, chroma, contrast and colour-vision-
# deficiency separation (OKLab delta-E, light mode):
#   segments  coral / orchid / teal / indigo  (--pairs all: normal-vision dE >= 18.7, contrast >= 3:1, CVD 7.9 -> always
#             direct-labelled) - defined once in custseg.viz.SEGMENT_PALETTE and read from mart.segment_profile.color
#   series    denim PRIMARY + amber-gold SECOND (adjacent: dE 30.9, CVD 27.0, contrast >= 3:1)
PRIMARY, PRIMARY_SOFT, SECOND = "#3A5BA0", "#A9B9DD", "#C2851A"
NAVY, NAVY_2, NAVY_SUB = "#25242A", "#36343C", "#CFCAC2"          # header: warm charcoal band, pill, warm-grey subtitle
HEADER_LINE = "#C2851A"                                              # amber-gold line under the header
INK, INK2, MUTED = "#1B2233", "#4A5367", "#8A92A6"
CANVAS, CARD, BORDER, GRID = "#F2F4F8", "#FFFFFF", "#E2E6EF", "#ECEFF5"
TABLE_HEAD, TABLE_ALT = "#F1F3F9", "#F8F9FC"
CRITICAL = "#C8423B"                                                 # status only: churn, shrinking segment
NEUTRAL = "#C5CAD6"
SEGMENTS = {"At Risk": "#D9653B", "Hibernating": "#C266C0", "New Customers": "#139C85", "Loyal Customers": "#3558D4"}
COHORT_RAMP = ["#EEF1FA", "#C7D2F0", "#8DA2E0", "#4D6BC6", "#26408F"]  # one hue (indigo), light -> dark
RUPIAH = '"Rp" #,0'                                                  # Rupiah; separators follow model culture id-ID
# legacy names used by the page functions: single-series = PRIMARY, second series = SECOND; KPI-card accent bars are
# decoration only, so every card uses the same brand accent instead of competing hues
BLUE, ORANGE = PRIMARY, SECOND
ACCENT = HEADER_LINE
AQUA = YELLOW = MAGENTA = GREEN = VIOLET = RED = ACCENT

TABLES = ["dim_customer", "dim_location", "dim_product", "dim_date", "dim_payment_method", "fact_sales", "fact_orders",
          "segment_profile", "segment_migration", "period_retention", "cohort_retention", "product_affinity",
          "kpi_monthly", "kpi_dictionary", "model_comparison", "category_by_segment", "revenue_pareto", "meta"]
RELATIONSHIPS = [  # (from many-side, to one-side) - all single direction
    ("fact_sales.customer_key", "dim_customer.customer_key"),
    ("fact_sales.product_key", "dim_product.product_key"),
    ("fact_sales.date_key", "dim_date.date_key"),
    ("fact_sales.payment_method_key", "dim_payment_method.payment_method_key"),
    ("fact_orders.customer_key", "dim_customer.customer_key"),
    ("fact_orders.date_key", "dim_date.date_key"),
    ("fact_orders.payment_method_key", "dim_payment_method.payment_method_key"),
    ("dim_customer.location_key", "dim_location.location_key"),
]
TYPE_MAP = {"bigint": "int64", "integer": "int64", "smallint": "int64", "double precision": "double", "real": "double",
            "numeric": "double", "text": "string", "character varying": "string", "boolean": "boolean",
            "timestamp without time zone": "dateTime", "timestamp with time zone": "dateTime", "date": "dateTime"}
PCT_COLS = {"customer_share", "revenue_contribution", "retention_rate", "churn_rate", "late_delivery_share",
            "segment_growth_rate", "reactivation_rate", "support", "confidence", "p_alive", "acquisition_rate",
            "customer_growth_rate", "revenue_growth_mom", "cum_revenue_share", "customer_pct"}
BRL_COLS = {"revenue", "monetary", "avg_monetary", "avg_order_value", "avg_historical_clv", "historical_clv",
            "line_total", "order_value", "unit_price", "freight_value", "revenue_per_customer",
            "predicted_clv_12m", "avg_predicted_clv_12m"}
SORT_BY = {("dim_customer", "segment_name"): "segment_id", ("dim_date", "day_name"): "day_of_week",
           ("period_retention", "period"): "period_start", ("dim_date", "month_name"): "month",
           ("segment_profile", "segment_name"): "segment_id", ("dim_customer", "clv_band"): "clv_band_order",
           ("dim_customer", "inactivity_band"): "inactivity_band_order", ("dim_customer", "clv_tier"): "clv_tier_order"}
HIDDEN = {"customer_key", "location_key", "product_key", "date_key", "payment_method_key", "sales_key", "order_key",
          "segment_color", "color", "clv_band_order", "inactivity_band_order", "clv_tier_order"}

DC, FS, FO, SP, PR = "'dim_customer'", "'fact_sales'", "'fact_orders'", "'segment_profile'", "'period_retention'"
MEASURES = [
    # ---- fact_sales
    ("fact_sales", "Total Revenue", f"SUM({FS}[line_total])", RUPIAH),
    ("fact_sales", "Total Orders", f"DISTINCTCOUNT({FS}[order_key])", "#,0"),
    ("fact_sales", "Total Customers", f"DISTINCTCOUNT({FS}[customer_key])", "#,0"),
    ("fact_sales", "Items Sold", f"SUM({FS}[quantity])", "#,0"),
    ("fact_sales", "Average Order Value", "DIVIDE([Total Revenue], [Total Orders])", RUPIAH),
    ("fact_sales", "Average Revenue per Customer", "DIVIDE([Total Revenue], [Total Customers])", RUPIAH),
    ("fact_sales", "Purchase Frequency", "DIVIDE([Total Orders], [Total Customers])", "0.000"),
    ("fact_sales", "Average Basket Size", "DIVIDE([Items Sold], [Total Orders])", "0.00"),
    ("fact_sales", "Revenue Contribution",
     # segment_name is sorted by segment_id: both must be cleared, otherwise every segment = 100%
     f"DIVIDE([Total Revenue], CALCULATE([Total Revenue], REMOVEFILTERS({DC}[segment_name], {DC}[segment_id])))", "0.0%"),
    ("fact_sales", "Segment Distribution",
     f"DIVIDE([Total Customers], CALCULATE([Total Customers], REMOVEFILTERS({DC}[segment_name], {DC}[segment_id])))", "0.0%"),
    ("fact_sales", "Revenue Label",
     "VAR v = [Total Revenue] RETURN SWITCH(TRUE(), ISBLANK(v), \"–\", "
     "v >= 1e12, \"Rp \" & FORMAT(v / 1e12, \"#,0.00\") & \" triliun\", v >= 1e9, \"Rp \" & FORMAT(v / 1e9, \"#,0.0\") & \" miliar\", "
     "v >= 1e7, \"Rp \" & FORMAT(v / 1e6, \"#,0.0\") & \" juta\", \"Rp \" & FORMAT(v, \"#,0\"))", None),
    ("fact_sales", "Revenue (Rp miliar)", "DIVIDE([Total Revenue], 1e9)", "#,0.0"),
    ("fact_sales", "AOV (Rp ribu)", "DIVIDE([Average Order Value], 1e3)", "0"),      # no grouping: unambiguous
    ("fact_sales", "Avg Spend (Rp ribu)", "DIVIDE([Average Revenue per Customer], 1e3)", "0"),
    ("fact_sales", "Top 10 Revenue",
     f"VAR r = RANKX(ALLSELECTED({DC}[customer_code]), [Total Revenue], , DESC) RETURN IF(r <= 10, [Total Revenue])",
     RUPIAH),
    # ---- fact_orders
    ("fact_orders", "Orders", f"COUNTROWS({FO})", "#,0"),
    ("fact_orders", "New Customers", f"CALCULATE(DISTINCTCOUNT({FO}[customer_key]), {FO}[is_first_order] = 1)", "#,0"),
    ("fact_orders", "Returning Customers", f"CALCULATE(DISTINCTCOUNT({FO}[customer_key]), {FO}[is_first_order] = 0)", "#,0"),
    ("fact_orders", "Average Review Score", f"AVERAGE({FO}[review_score])", "0.00"),
    ("fact_orders", "Late Delivery Share", f"AVERAGE({FO}[is_late])", "0.0%"),
    ("fact_orders", "Average Delivery Days", f"AVERAGE({FO}[delivery_days])", "0.0"),
    ("fact_orders", "Average Installments", f"AVERAGE({FO}[installments])", "0.00"),
    # ---- dim_customer (customer snapshot at the analysis date)
    ("dim_customer", "Customers (Snapshot)", f"COUNTROWS({DC})", "#,0"),
    ("dim_customer", "Active Customers", f"CALCULATE(COUNTROWS({DC}), {DC}[is_churned] = 0)", "#,0"),
    ("dim_customer", "Churned Customers", f"CALCULATE(COUNTROWS({DC}), {DC}[is_churned] = 1)", "#,0"),
    ("dim_customer", "Churn Rate (Inactivity)", "DIVIDE(COALESCE([Churned Customers], 0), [Customers (Snapshot)])", "0.0%"),
    ("dim_customer", "Active Customer Rate", "DIVIDE([Active Customers], [Customers (Snapshot)])", "0.0%"),
    ("dim_customer", "Repeat Purchase Rate", f"DIVIDE(SUM({DC}[is_repeat]), [Customers (Snapshot)])", "0.00%"),
    ("dim_customer", "Historical CLV", f"AVERAGE({DC}[historical_clv])", RUPIAH),
    ("dim_customer", "Predicted CLV 12m", f"AVERAGE({DC}[predicted_clv_12m])", RUPIAH),
    ("dim_customer", "Historical CLV (Rp ribu)", "DIVIDE([Historical CLV], 1e3)", "0"),
    ("dim_customer", "Average Recency (days)", f"AVERAGE({DC}[recency_days])", "#,0"),
    ("dim_customer", "Average Purchase Interval", f"AVERAGE({DC}[avg_purchase_interval_days])", "#,0 \"days\""),
    ("dim_customer", "Segment Color", f"SELECTEDVALUE({DC}[segment_color], \"{NEUTRAL}\")", None),
    ("dim_customer", "High-Value At-Risk Revenue",
     f"CALCULATE(SUM({DC}[monetary]), {DC}[is_high_value_at_risk] = 1)", RUPIAH),
    ("dim_customer", "High-Value At-Risk Customers", f"CALCULATE(COUNTROWS({DC}), {DC}[is_high_value_at_risk] = 1)", "#,0"),
    ("dim_customer", "High-Potential CLV", f"CALCULATE(SUM({DC}[predicted_clv_12m]), {DC}[is_high_potential] = 1)",
     RUPIAH),
    ("dim_customer", "High-Potential Customers", f"CALCULATE(COUNTROWS({DC}), {DC}[is_high_potential] = 1)", "#,0"),
    # ---- period retention (3-month periods)
    ("period_retention", "Retention Rate", f"DIVIDE(SUM({PR}[retained_customers]), SUM({PR}[eligible_customers]))", "0.00%"),
    ("period_retention", "Churn Rate", "1 - [Retention Rate]", "0.00%"),
    ("period_retention", "Reactivation Rate",
     f"DIVIDE(SUM({PR}[reactivated_customers]), SUM({PR}[inactive_customers]))", "0.00%"),
    ("period_retention", "Reactivated Customers", f"SUM({PR}[reactivated_customers])", "#,0"),
    # ---- other
    ("cohort_retention", "Cohort Retention", "DIVIDE(SUM('cohort_retention'[active_customers]), "
                                             "SUM('cohort_retention'[cohort_size]))", "0.00%"),
    ("cohort_retention", "Cohort Cell Color",
     f"VAR v = [Cohort Retention] RETURN SWITCH(TRUE(), ISBLANK(v), \"#ffffff\", v >= 0.006, \"{COHORT_RAMP[4]}\", "
     f"v >= 0.004, \"{COHORT_RAMP[3]}\", v >= 0.0025, \"{COHORT_RAMP[2]}\", v >= 0.0012, \"{COHORT_RAMP[1]}\", "
     f"v > 0, \"{COHORT_RAMP[0]}\", \"#ffffff\")", None),
    ("cohort_retention", "Cohort Text Color",
     f"IF([Cohort Retention] >= 0.004, \"#ffffff\", \"{INK}\")", None),
    ("segment_profile", "Profile Color", f"SELECTEDVALUE({SP}[color], \"{NEUTRAL}\")", None),
    ("segment_profile", "Growth Color",
     f"VAR g = SELECTEDVALUE({SP}[segment_growth_rate]) RETURN IF(g < 0, \"{CRITICAL}\", \"{PRIMARY}\")", None),
    ("revenue_pareto", "Top 10% Revenue Share",
     "CALCULATE(MAX('revenue_pareto'[cum_revenue_share]), 'revenue_pareto'[customer_pct] = 0.10)", "0.0%"),
    ("revenue_pareto", "Top 20% Revenue Share",
     "CALCULATE(MAX('revenue_pareto'[cum_revenue_share]), 'revenue_pareto'[customer_pct] = 0.20)", "0.0%"),
    ("meta", "Data As Of",
     "\"Data as of \" & FORMAT(MAX('meta'[analysis_date]), \"dd mmm yyyy\") & \"  ·  refreshed \" & "
     "FORMAT(MAX('meta'[refreshed_at]), \"dd mmm yyyy hh:nn\")", None),
    ("meta", "Campaign Note", "\"Campaign performance: not available — the Olist dataset contains no campaign history. "
                              "Measure each strategy with an A/B test against a hold-out group.\"", None),
]


def fx_rate() -> float:
    """Fixed BRL->IDR rate used by the pbi views (stored in pbi.meta by the pipeline)."""
    return float(db.query("SELECT fx_brl_idr FROM pbi.meta").iloc[0, 0])


def id_label(field):
    """Return a text measure that shows `field` with Indonesian formatting (model culture id-ID): 93.104 ·
    Rp 643.296 · 3,00% · 80 hari. Visual number formats follow the viewer's Power BI locale; FORMAT follows the
    model culture, so KPI cards always read the Indonesian way."""
    if "Measure" not in field:
        return field
    table, name = field["Measure"]["Expression"]["SourceRef"]["Entity"], field["Measure"]["Property"]
    fmt = next((m[3] for m in MEASURES if m[1] == name), None)
    if fmt is None or name.endswith("(label)"):
        return field                                    # already text
    lname = f"{name} (label)"
    if not any(m[1] == lname for m in MEASURES):
        if fmt == RUPIAH:
            body = ('SWITCH(TRUE(), v >= 1e9, "Rp " & FORMAT(v / 1e9, "#,0.0") & " miliar", '
                    'v >= 1e7, "Rp " & FORMAT(v / 1e6, "#,0.0") & " juta", "Rp " & FORMAT(v, "#,0"))')
        elif "days" in fmt:
            body = 'FORMAT(v, "#,0") & " hari"'
        else:
            body = f'FORMAT(v, "{fmt}")'
        MEASURES.append((table, lname, f'VAR v = [{name}] RETURN IF(ISBLANK(v), "–", {body})', None))
    return meas(table, lname)


_GUID_NS = uuid.UUID("5b1c6f0e-3a51-4c1e-9d2f-6c0a8e7b4d21")
_guid_counter = [0]


def guid() -> str:
    """Deterministic lineage tags: identical rebuilds produce identical files (clean git diffs)."""
    _guid_counter[0] += 1
    return str(uuid.uuid5(_GUID_NS, f"{NAME}-{_guid_counter[0]}"))


def q(name: str) -> str:
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ============================================================================================ semantic model
def table_columns(table: str) -> list[tuple[str, str]]:
    d = db.query("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='pbi' "
                 "AND table_name=:t ORDER BY ordinal_position", t=table)
    if d.empty:
        raise SystemExit(f"view pbi.{table} not found - run `python -m custseg.pipeline` first")
    return list(d.itertuples(index=False, name=None))


def fmt_for(col_, dt):
    if col_ in ("month_start", "cohort_month"):
        return "mmm yy"
    if col_ in PCT_COLS:
        return "0.0%"
    if col_ in BRL_COLS:
        return RUPIAH
    if dt == "dateTime":
        return "yyyy-mm-dd"
    if dt == "double":
        return "#,0.00"
    if dt == "int64":
        return "#,0"
    return None


def build_semantic_model() -> None:
    d = SM / "definition"
    dump(SM / "definition.pbism", {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                   "version": "4.2", "settings": {}})
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    order = json.dumps(["PgServer", "PgDatabase"] + TABLES)
    write(d / "model.tmdl", "model Model\n\tculture: id-ID\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
                            "\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n"
                            "\t\treturnErrorValuesAsNull\n\n"
                            f"annotation PBI_QueryOrder = {order}\n\n"
                            "annotation __PBI_TimeIntelligenceEnabled = 0\n\n"
                            + "".join(f"ref table {q(t)}\n" for t in TABLES))
    write(d / "expressions.tmdl",
          f'expression PgServer = "{config.PG_HOST}:{config.PG_PORT}" meta [IsParameterQuery=true, Type="Text", '
          f'IsParameterQueryRequired=true]\n\tlineageTag: {guid()}\n\n\tannotation PBI_ResultType = Text\n\n'
          f'expression PgDatabase = "{config.PG_DB}" meta [IsParameterQuery=true, Type="Text", '
          f'IsParameterQueryRequired=true]\n\tlineageTag: {guid()}\n\n\tannotation PBI_ResultType = Text\n')
    rel = []
    for f, t in RELATIONSHIPS:
        rel += [f"relationship {guid()}", f"\tfromColumn: {f}", f"\ttoColumn: {t}", ""]
    write(d / "relationships.tmdl", "\n".join(rel))
    for t in TABLES:
        lines = [f"table {q(t)}", f"\tlineageTag: {guid()}", ""]
        for name, mexpr, fmt in [(m[1], m[2], m[3]) for m in MEASURES if m[0] == t]:
            lines.append(f"\tmeasure {q(name)} = {mexpr}")
            if fmt:
                lines.append(f"\t\tformatString: {fmt}")
            lines += [f"\t\tlineageTag: {guid()}", ""]
        for col_, pgtype in table_columns(t):
            dt = TYPE_MAP[pgtype]
            lines.append(f"\tcolumn {q(col_)}")
            lines.append(f"\t\tdataType: {dt}")
            f_ = fmt_for(col_, dt)
            if f_:
                lines.append(f"\t\tformatString: {f_}")
            if col_ in HIDDEN or col_.endswith("_key"):
                lines.append("\t\tisHidden")
            if (t, col_) in SORT_BY:
                lines.append(f"\t\tsortByColumn: {SORT_BY[(t, col_)]}")
            if t == "dim_location" and col_ == "city":
                lines.append("\t\tdataCategory: City")
            if t == "dim_location" and col_ == "state":
                lines.append("\t\tdataCategory: StateOrProvince")
            summ = "none" if (dt not in ("int64", "double") or col_.endswith("_key") or col_ in
                              ("r_score", "f_score", "m_score", "rfm_score", "month_index", "purchase_hour",
                               "day_of_week", "month", "year", "quarter", "is_first_order")) else "sum"
            lines += [f"\t\tlineageTag: {guid()}", f"\t\tsummarizeBy: {summ}", f"\t\tsourceColumn: {col_}", "",
                      "\t\tannotation SummarizationSetBy = Automatic", ""]
        lines += [f"\tpartition {q(t)} = m", "\t\tmode: directQuery", "\t\tsource =",
                  "\t\t\t\tlet", "\t\t\t\t    Source = PostgreSQL.Database(PgServer, PgDatabase),",
                  f'\t\t\t\t    Data = Source{{[Schema="pbi",Item="{t}"]}}[Data]', "\t\t\t\tin", "\t\t\t\t    Data",
                  "", "\tannotation PBI_ResultType = Table", ""]
        write(d / "tables" / f"{t}.tmdl", "\n".join(lines))
    # human-readable copy of every measure (PRD 10.2 deliverable)
    dax = ["// DAX measures of the CustomerSegmentation semantic model (generated by build_pbip.py)", ""]
    for t, n, e, f in MEASURES:
        dax += [f"// table: {t}" + (f"   format: {f}" if f else ""), f"[{n}] =", f"    {e}", ""]
    write(OUT / "dax_measures" / "measures.dax", "\n".join(dax))
    rel_md = ["# Data model", "", "Star schema, DirectQuery on PostgreSQL schema `pbi` (localhost:5435 / custsegdb).", "",
              "| From (many) | To (one) | Direction |", "|---|---|---|"]
    rel_md += [f"| `{f}` | `{t}` | single |" for f, t in RELATIONSHIPS]
    rel_md += ["", "Disconnected (pre-aggregated) tables: " + ", ".join(f"`{t}`" for t in TABLES
                                                                       if t not in {x.split('.')[0] for r in RELATIONSHIPS for x in r}),
               "", "Filter propagation: `dim_location -> dim_customer -> fact_sales / fact_orders`; "
               "`dim_date`, `dim_product`, `dim_payment_method -> facts`. The product-category slicer filters "
               "`fact_sales` only (order-level experience measures on `fact_orders` are category-agnostic by design)."]
    write(OUT / "data_model" / "data_model.md", "\n".join(rel_md) + "\n")


# ============================================================================================ query helpers
def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def color(hex_: str):
    return {"solid": {"color": lit(hex_)}}


def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def meas(table, name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def color_by(table, measure):
    return {"solid": {"color": {"expr": meas(table, measure)}}}


AGG = {"sum": 0, "avg": 1, "count": 2, "min": 3, "max": 4}


def agg(table, column, fn="sum"):
    return {"Aggregation": {"Expression": col(table, column), "Function": AGG[fn]}}


def ref_of(field) -> str:
    if "Column" in field or "Measure" in field:
        c = field.get("Column") or field.get("Measure")
        return f"{c['Expression']['SourceRef']['Entity']}.{c['Property']}"
    c = field["Aggregation"]
    inner = c["Expression"]["Column"]
    fn = {0: "Sum", 1: "Avg", 2: "Count", 3: "Min", 4: "Max"}[c["Function"]]
    return f"{fn}({inner['Expression']['SourceRef']['Entity']}.{inner['Property']})"


def proj(field, display=None):
    ref = ref_of(field)
    native = ref.split(".", 1)[1].rstrip(")") if "(" not in ref.split(".")[0] else ref
    p = {"field": field, "queryRef": ref, "nativeQueryRef": native}
    if display:
        p["displayName"] = display
    return p


WILDCARD = {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}


def card_container(title=None, bg=CARD, border=True, radius=12, pad=(12, 10, 16, 16), tooltip_page=None):
    o = {"background": [{"properties": {"show": lit(True), "color": color(bg), "transparency": lit(0)}}],
         "border": [{"properties": {"show": lit(border), "color": color(BORDER), "radius": lit(radius), "width": lit(1)}}],
         "padding": [{"properties": {"top": lit(pad[0]), "bottom": lit(pad[1]), "left": lit(pad[2]), "right": lit(pad[3])}}],
         "dropShadow": [{"properties": {"show": lit(False)}}],
         "subTitle": [{"properties": {"show": lit(False)}}],
         "visualHeader": [{"properties": {"show": lit(True)}}]}
    if title:
        o["title"] = [{"properties": {"show": lit(True), "text": lit(title), "fontColor": color(INK), "fontSize": lit(11),
                                      "bold": lit(False), "fontFamily": lit("Segoe UI Semibold")}}]
    else:
        o["title"] = [{"properties": {"show": lit(False)}}]
    if tooltip_page:
        o["visualTooltip"] = [{"properties": {"show": lit(True), "type": lit("ReportPage"),
                                              "section": lit(tooltip_page)}}]
    return o


# ============================================================================================ page builder
class Page:
    def __init__(self, name, display, subtitle, kind=None, size=(W, H), header=True):
        self.name, self.display, self.subtitle, self.kind = name, display, subtitle, kind
        self.w, self.h = size
        self.visuals: list[dict] = []
        self.filters: list[dict] = []
        self.binding = None
        if header:
            self._header()

    def add(self, name, x, y, w, h, visual, container=None):
        visual["visualContainerObjects"] = container if container is not None else card_container()
        visual.setdefault("drillFilterOtherVisuals", True)
        self.visuals.append({
            "$schema": f"{SCHEMA}/item/report/definition/visualContainer/{V_VISUAL}/schema.json", "name": name,
            "position": {"x": x, "y": y, "z": len(self.visuals) * 1000, "width": w, "height": h,
                         "tabOrder": len(self.visuals) * 1000},
            "visual": visual})

    def text(self, name, x, y, w, h, paragraphs, bg=None):
        runs = [{"textRuns": [{"value": t, "textStyle": {"fontWeight": wgt, "fontSize": f"{size}pt", "color": c,
                                                           "fontFamily": "Segoe UI"}}]} for t, size, wgt, c in paragraphs]
        cont = card_container(bg=bg or CARD, border=False, radius=0, pad=(6, 4, 8, 8))
        cont["visualHeader"] = [{"properties": {"show": lit(False)}}]
        if bg is None:
            cont["background"] = [{"properties": {"show": lit(False)}}]
        self.add(name, x, y, w, h, {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": runs}}]}},
                 cont)

    def bar(self, name, x, y, w, h, hex_):
        cont = card_container(bg=hex_, border=False, radius=2, pad=(0, 0, 0, 0))
        cont["visualHeader"] = [{"properties": {"show": lit(False)}}]
        self.add(name, x, y, w, h, {"visualType": "textbox",
                                    "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": " "}]}]}}]}},
                 cont)

    def _header(self):
        self.text("hdr_band", 0, 0, self.w, HEADER_H,
                  [(self.display, 16, "bold", "#ffffff"), (self.subtitle, 9, "normal", NAVY_SUB)], bg=NAVY)
        pill = card_container(bg=NAVY_2, border=False, radius=17, pad=(4, 4, 12, 12))
        pill["visualHeader"] = [{"properties": {"show": lit(False)}}]
        self.add("hdr_asof", self.w - M - 340, 15, 340, 34, {
            "visualType": "card", "query": {"queryState": {"Values": {"projections": [proj(meas("meta", "Data As Of"))]}}},
            "objects": {"labels": [{"properties": {"fontSize": lit(9), "color": color(NAVY_SUB), "fontFamily": lit("Segoe UI")}}],
                        "categoryLabels": [{"properties": {"show": lit(False)}}]}}, pill)
        self.bar("hdr_line", 0, HEADER_H, self.w, 4, HEADER_LINE)

    def card(self, name, x, y, w, h, field, label, size=18, value_color=INK, value_color_measure=None, bg=CARD,
             border=True, show_label=True):
        vc = color_by(*value_color_measure) if value_color_measure else color(value_color)
        cont = card_container(bg=bg, border=border, pad=(6, 6, 14, 10))
        cont["visualHeader"] = [{"properties": {"show": lit(False)}}]
        self.add(name, x, y, w, h, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [proj(field, label)]}}},
            "objects": {"labels": [{"properties": {"fontSize": lit(size), "color": vc, "labelDisplayUnits": lit(1),
                                                   "fontFamily": lit("Segoe UI Semibold")}}],
                        "categoryLabels": [{"properties": {"show": lit(show_label), "fontSize": lit(9),
                                                           "color": color(MUTED), "fontFamily": lit("Segoe UI")}}]}}, cont)

    def kpis(self, y, items, h=78):
        n = len(items)
        w = (self.w - 2 * M - (n - 1) * G) / n
        for i, it in enumerate(items):
            name, field, label, accent = it[:4]
            extra = it[4] if len(it) > 4 else {}
            x = round(M + i * (w + G))
            self.card(name, x, y, round(w), h, id_label(field), label, **extra)
            self.bar(f"{name}_accent", x + 1, y + 14, 3, h - 28, ACCENT)   # one brand accent for every card

    def slicer(self, name, x, y, w, h, field, title, mode="Dropdown"):
        cont = card_container(None, border=False, pad=(0, 0, 2, 2))
        cont["background"] = [{"properties": {"show": lit(False)}}]
        cont["visualHeader"] = [{"properties": {"show": lit(False)}}]
        self.add(name, x, y, w, h, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [proj(field, title)]}}},
            "objects": {"data": [{"properties": {"mode": lit(mode)}}],
                        "header": [{"properties": {"show": lit(True), "fontColor": color(MUTED), "textSize": lit(9),
                                                   "fontFamily": lit("Segoe UI Semibold"), "outline": lit("None")}}],
                        "items": [{"properties": {"fontSize": lit(10), "fontColor": color(INK),
                                                  "outline": lit("None")}}]}}, cont)

    def slicers(self, y, items, h=SLICER_H):
        """Filter bar: one rounded white card across the page, FILTER caption, evenly spaced borderless slicers."""
        bar = card_container(None, pad=(0, 0, 0, 0))
        bar["visualHeader"] = [{"properties": {"show": lit(False)}}]
        self.add("filter_bar", M, y, self.w - 2 * M, h, {"visualType": "textbox", "objects": {"general": [
            {"properties": {"paragraphs": [{"textRuns": [{"value": " "}]}]}}]}}, bar)
        self.text("filter_caption", M + 10, y + 10, 92, h - 20, [("⧩  FILTER", 10, "bold", HEADER_LINE)])
        x0, gap = M + 110, 18
        n = len(items)
        w = (self.w - M - 14 - x0 - (n - 1) * gap) / n
        for i, (name, field, title, *mode) in enumerate(items):
            self.slicer(name, round(x0 + i * (w + gap)), y + 5, round(w), h - 10, field, title, *(mode or []))

    def chart(self, name, x, y, w, h, vtype, roles: dict, title, objects=None, sort=None, tooltip_page=None):
        qs = {role: {"projections": [proj(f, d) for f, d in fields]} for role, fields in roles.items()}
        query = {"queryState": qs}
        if sort:
            field, direction = sort
            query["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": False}
        self.add(name, x, y, w, h, {"visualType": vtype, "query": query, "objects": objects or {}},
                 card_container(title, tooltip_page=tooltip_page))

    def drillthrough_on(self, field, filter_name="dt_filter"):
        self.kind = "Drillthrough"
        self.filters.append({"name": filter_name, "field": field, "type": "Categorical", "howCreated": "Drillthrough"})
        self.binding = {"name": f"{self.name}_binding", "type": "Drillthrough",
                        "parameters": [{"name": f"{self.name}_param", "boundFilter": filter_name, "fieldExpr": field}]}

    def tooltip_on(self, field, filter_name="tt_filter"):
        self.kind = "Tooltip"
        self.filters.append({"name": filter_name, "field": field, "type": "Categorical", "howCreated": "User"})
        self.binding = {"name": f"{self.name}_binding", "type": "Tooltip",
                        "parameters": [{"name": f"{self.name}_param", "boundFilter": filter_name, "fieldExpr": field}]}

    def write(self, root: Path):
        pdir = root / "pages" / self.name
        objects = {"background": [{"properties": {"color": color(CANVAS), "transparency": lit(0)}}],
                   "outspace": [{"properties": {"color": color(CANVAS)}}]}
        page = {"$schema": f"{SCHEMA}/item/report/definition/page/{V_PAGE}/schema.json",
                "name": self.name, "displayName": self.display, "displayOption": "FitToPage",
                "height": self.h, "width": self.w, "objects": objects}
        if self.filters:
            page["filterConfig"] = {"filters": self.filters}
        if self.binding:
            page["pageBinding"] = self.binding
        if self.kind:
            page["type"] = self.kind
        if self.kind == "Tooltip":
            page["visibility"] = "HiddenInViewMode"
            page["displayOption"] = "ActualSize"
        dump(pdir / "page.json", page)
        for v in self.visuals:
            dump(pdir / "visuals" / v["name"] / "visual.json", v)


# ---- formatting presets ---------------------------------------------------------------------------------
def axis_fmt(hide_value_axis=False):
    cat = {"fontSize": lit(9), "labelColor": color(INK2), "showAxisTitle": lit(False), "gridlineShow": lit(False)}
    val = {"fontSize": lit(9), "labelColor": color(MUTED), "showAxisTitle": lit(False),
           "gridlineColor": color(GRID), "gridlineStyle": lit("solid")}
    if hide_value_axis:
        val["show"] = lit(False)
    return {"categoryAxis": [{"properties": cat}], "valueAxis": [{"properties": val}]}


def legend(show=True):
    return {"legend": [{"properties": {"show": lit(show), "position": lit("TopRight"), "fontSize": lit(9),
                                       "labelColor": color(INK2), "showTitle": lit(False)}}]}


def bars(fill=BLUE, fill_measure=None):
    o = axis_fmt(hide_value_axis=True)
    o["labels"] = [{"properties": {"show": lit(True), "color": color(INK2), "fontSize": lit(9),
                                   "labelDisplayUnits": lit(1)}}]
    if fill_measure:
        o["dataPoint"] = [{"properties": {"fill": color_by(*fill_measure)}, "selector": WILDCARD}]
    else:
        o["dataPoint"] = [{"properties": {"fill": color(fill)}}]
    o.update(legend(False))
    return o


def series_colors(mapping: dict):
    return [{"selector": {"metadata": ref}, "properties": {"fill": color(c)}} for ref, c in mapping.items()]


def lines(mapping: dict, markers=False):
    o = axis_fmt()
    o["dataPoint"] = series_colors(mapping)
    o["lineStyles"] = [{"properties": {"strokeWidth": lit(2), "showMarker": lit(markers), "lineChartType": lit("linear")}}]
    o.update(legend(len(mapping) > 1))
    return o


def table_fmt(widths: dict | None = None, table=None, wrap=False, extra_values=None):
    o = {"columnHeaders": [{"properties": {"fontColor": color(INK2), "backColor": color(TABLE_HEAD), "fontSize": lit(9),
                                           "wordWrap": lit(True), "bold": lit(False), "fontFamily": lit("Segoe UI Semibold")}}],
         "total": [{"properties": {"totals": lit(False)}}],
         "values": [{"properties": {"fontSize": lit(9), "fontColorPrimary": color(INK), "fontColorSecondary": color(INK),
                                    "wordWrap": lit(wrap), "backColorPrimary": color(CARD),
                                    "backColorSecondary": color(TABLE_ALT)}}] + (extra_values or []),
         "grid": [{"properties": {"gridHorizontal": lit(True), "gridHorizontalColor": color(GRID),
                                  "gridVertical": lit(False), "rowPadding": lit(4)}}]}
    if widths:
        o["columnWidth"] = [{"properties": {"value": lit(v)}, "selector": {"metadata": k}} for k, v in widths.items()]
    return o


def scatter_fmt(fill_measure):
    sc = axis_fmt()
    sc["valueAxis"][0]["properties"]["showAxisTitle"] = lit(True)
    sc["valueAxis"][0]["properties"]["labelDisplayUnits"] = lit(1)
    sc["categoryAxis"][0]["properties"]["showAxisTitle"] = lit(True)
    sc["dataPoint"] = [{"properties": {"fill": color_by(*fill_measure)}, "selector": WILDCARD}]
    sc["categoryLabels"] = [{"properties": {"show": lit(True), "fontSize": lit(8), "color": color(INK2)}}]
    sc.update(legend(False))
    return sc


def grid_cols(n, total=W - 2 * M, x0=M):
    w = (total - (n - 1) * G) / n
    return [(round(x0 + i * (w + G)), round(w)) for i in range(n)]


TOOLTIP = "segment_tooltip"


# ============================================================================================ pages
def global_slicers(p: Page, y):
    p.slicers(y, [("sl_date", col("dim_date", "year_month"), "Month"),
                  ("sl_region", col("dim_location", "region"), "Region"),
                  ("sl_state", col("dim_location", "state"), "State"),
                  ("sl_segment", col("dim_customer", "segment_name"), "Customer segment"),
                  ("sl_category", col("dim_product", "category_group"), "Product category")])


def page_executive() -> Page:
    p = Page("executive_overview", "1 · Executive Customer Overview",
             "Olist delivered orders Jan 2017 – Aug 2018 · revenue = items + freight (no cost data → no profit) · "
             "nilai dalam Rupiah, kurs tetap Rp " + f"{fx_rate():,.0f}".replace(",", ".") + "/BRL")
    y = HEADER_H + 12
    global_slicers(p, y)
    y1 = y + SLICER_H + G
    p.kpis(y1, [
        ("kpi_customers", meas("fact_sales", "Total Customers"), "Purchasing customers", BLUE),
        ("kpi_active", meas("dim_customer", "Active Customers"), "Active customers (≤ T days)", AQUA),
        ("kpi_new", meas("fact_orders", "New Customers"), "New customers", VIOLET),
        ("kpi_revenue", meas("fact_sales", "Revenue Label"), "Total revenue", GREEN),
        ("kpi_aov", meas("fact_sales", "Average Order Value"), "Average order value", ORANGE),
        ("kpi_repeat", meas("dim_customer", "Repeat Purchase Rate"), "Repeat purchase rate", MAGENTA),
    ])
    y2, h2 = y1 + 78 + G, 255
    (x1, w1), (x2, w2) = grid_cols(2)
    p.chart("revenue_trend", x1, y2, w1, h2, "areaChart",
            {"Category": [(col("dim_date", "month_start"), "Month")], "Y": [(meas("fact_sales", "Revenue (Rp miliar)"), "Revenue")]},
            "Monthly revenue trend (Rp miliar)", lines({"fact_sales.Revenue (Rp miliar)": BLUE}))
    st = axis_fmt()
    st["dataPoint"] = series_colors({"fact_orders.New Customers": BLUE, "fact_orders.Returning Customers": ORANGE})
    st.update(legend(True))
    p.chart("customer_growth", x2, y2, w2, h2, "columnChart",
            {"Category": [(col("dim_date", "month_start"), "Month")],
             "Y": [(meas("fact_orders", "New Customers"), "New"), (meas("fact_orders", "Returning Customers"), "Returning")]},
            "Customer growth · new vs returning customers per month", st)
    y3 = y2 + h2 + G
    h3 = H - y3 - M
    p.chart("dist_segment", x1, y3, w1, h3, "clusteredBarChart",
            {"Category": [(col("dim_customer", "segment_name"), "Segment")], "Y": [(meas("fact_sales", "Total Customers"), "Customers")]},
            "Customer distribution by segment", bars(fill_measure=("dim_customer", "Segment Color")),
            sort=(meas("fact_sales", "Total Customers"), "Descending"), tooltip_page=TOOLTIP)
    p.chart("contrib_segment", x2, y3, w2, h3, "clusteredBarChart",
            {"Category": [(col("dim_customer", "segment_name"), "Segment")],
             "Y": [(meas("fact_sales", "Revenue Contribution"), "Revenue contribution")]},
            "Revenue contribution by segment (% of revenue)", bars(fill_measure=("dim_customer", "Segment Color")),
            sort=(meas("fact_sales", "Revenue Contribution"), "Descending"), tooltip_page=TOOLTIP)
    return p


def page_segmentation() -> Page:
    p = Page("segmentation_analysis", "2 · Customer Segmentation Analysis",
             "Final segments (selected model) · right-click a segment bar → Drill through → Customer Details")
    y = HEADER_H + 12
    p.slicers(y, [("sl_segment", col("dim_customer", "segment_name"), "Customer segment"),
                  ("sl_region", col("dim_location", "region"), "Region"),
                  ("sl_buyer", col("dim_customer", "buyer_type"), "Buyer type"),
                  ("sl_rfm", col("dim_customer", "rfm_segment"), "RFM rule-based segment (E1)")])
    y1 = y + SLICER_H + G
    p.kpis(y1, [
        ("kpi_cust", meas("dim_customer", "Customers (Snapshot)"), "Customers", BLUE),
        ("kpi_share", meas("fact_sales", "Segment Distribution"), "% of customers", AQUA),
        ("kpi_contrib", meas("fact_sales", "Revenue Contribution"), "% of revenue", GREEN),
        ("kpi_spend", meas("fact_sales", "Average Revenue per Customer"), "Avg spend / customer", ORANGE),
        ("kpi_freq", meas("fact_sales", "Purchase Frequency"), "Purchase frequency", VIOLET),
        ("kpi_rec", meas("dim_customer", "Average Recency (days)"), "Avg recency (days)", MAGENTA),
    ])
    y2, h2 = y1 + 78 + G, 230
    (a, aw), (b, bw), (c, cw) = grid_cols(3)
    p.chart("count_segment", a, y2, aw, h2, "clusteredBarChart",
            {"Category": [(col("dim_customer", "segment_name"), "Segment")], "Y": [(meas("dim_customer", "Customers (Snapshot)"), "Customers")]},
            "Customer count by segment", bars(fill_measure=("dim_customer", "Segment Color")),
            sort=(meas("dim_customer", "Customers (Snapshot)"), "Descending"), tooltip_page=TOOLTIP)
    p.chart("revenue_segment", b, y2, bw, h2, "clusteredBarChart",
            {"Category": [(col("dim_customer", "segment_name"), "Segment")], "Y": [(meas("fact_sales", "Revenue (Rp miliar)"), "Revenue")]},
            "Revenue by segment (Rp miliar)", bars(fill_measure=("dim_customer", "Segment Color")),
            sort=(meas("fact_sales", "Revenue (Rp miliar)"), "Descending"), tooltip_page=TOOLTIP)
    rfm = axis_fmt()
    rfm["dataPoint"] = [{"properties": {"fill": color(BLUE)}}]
    rfm.update(legend(False))
    p.chart("rfm_dist", c, y2, cw, h2, "columnChart",
            {"Category": [(col("dim_customer", "rfm_score"), "R+F+M score")],
             "Y": [(meas("dim_customer", "Customers (Snapshot)"), "Customers")]},
            "RFM score distribution (R + F + M)", rfm)
    y3 = y2 + h2 + G
    h3 = H - y3 - M
    sw = 300
    p.chart("scatter_rf", M, y3, sw, h3, "scatterChart",
            {"Category": [(col("segment_profile", "segment_name"), "Segment")],
             "X": [(agg("segment_profile", "avg_recency_days", "max"), "Avg recency (days)")],
             "Y": [(agg("segment_profile", "avg_frequency", "max"), "Avg frequency")],
             "Size": [(agg("segment_profile", "customers", "max"), "Customers")]},
            "Recency × Frequency (bubble size = customers)", scatter_fmt(("segment_profile", "Profile Color")))
    p.chart("scatter_fm", M + sw + G, y3, sw, h3, "scatterChart",
            {"Category": [(col("segment_profile", "segment_name"), "Segment")],
             "X": [(agg("segment_profile", "avg_frequency", "max"), "Avg frequency")],
             "Y": [(agg("segment_profile", "avg_monetary", "max"), "Avg monetary (Rp)")],
             "Size": [(agg("segment_profile", "customers", "max"), "Customers")]},
            "Frequency × Monetary (bubble size = customers)", scatter_fmt(("segment_profile", "Profile Color")))
    tx = M + 2 * (sw + G)
    sp = "segment_profile"
    p.chart("segment_matrix", tx, y3, W - M - tx, h3, "tableEx",
            {"Values": [(col(sp, "segment_name"), "Segment"), (agg(sp, "customers", "max"), "Customers"),
                        (agg(sp, "revenue_contribution", "max"), "% revenue"),
                        (agg(sp, "avg_order_value", "max"), "AOV"),
                        (agg(sp, "retention_rate", "max"), "Repeat rate"),
                        (agg(sp, "churn_rate", "max"), "Churn (inactive)"),
                        (agg(sp, "avg_predicted_clv_12m", "max"), "Pred. CLV")]},
            "Segment performance matrix", table_fmt(), sort=(agg(sp, "revenue_contribution", "max"), "Descending"))
    return p


def page_value() -> Page:
    p = Page("customer_value", "3 · Customer Value & CLV",
             "Historical CLV = revenue to date · Predicted CLV = BG/NBD × Gamma-Gamma, next 12 months (validated on a 6-month holdout)")
    y = HEADER_H + 12
    global_slicers(p, y)
    y1 = y + SLICER_H + G
    p.kpis(y1, [
        ("kpi_hclv", meas("dim_customer", "Historical CLV"), "Avg historical CLV", BLUE),
        ("kpi_pclv", meas("dim_customer", "Predicted CLV 12m"), "Avg predicted CLV (12 m)", VIOLET),
        ("kpi_spend", meas("fact_sales", "Average Revenue per Customer"), "Avg revenue / customer", GREEN),
        ("kpi_top10", meas("revenue_pareto", "Top 10% Revenue Share"), "Revenue from top 10% customers", ORANGE),
        ("kpi_top20", meas("revenue_pareto", "Top 20% Revenue Share"), "Revenue from top 20% customers", MAGENTA),
    ])
    y2, h2 = y1 + 78 + G, 250
    (a, aw), (b, bw), (c, cw) = grid_cols(3)
    hist = axis_fmt()
    hist["dataPoint"] = [{"properties": {"fill": color(BLUE)}}]
    hist["labels"] = [{"properties": {"show": lit(True), "color": color(INK2), "fontSize": lit(8), "labelDisplayUnits": lit(1)}}]
    p.chart("clv_dist", a, y2, aw, h2, "columnChart",
            {"Category": [(col("dim_customer", "clv_band"), "Historical CLV band")],
             "Y": [(meas("dim_customer", "Customers (Snapshot)"), "Customers")]},
            "Historical CLV distribution (customers)", hist, sort=(col("dim_customer", "clv_band"), "Ascending"))
    par = lines({"Max(revenue_pareto.cum_revenue_share)": BLUE})
    p.chart("pareto", b, y2, bw, h2, "lineChart",
            {"Category": [(col("revenue_pareto", "customer_pct"), "Share of customers (ranked by revenue)")],
             "Y": [(agg("revenue_pareto", "cum_revenue_share", "max"), "Cumulative revenue share")]},
            "Revenue Pareto (cumulative share)", par)
    cu = "dim_customer"
    p.chart("top10", c, y2, cw, h2, "tableEx",
            {"Values": [(col(cu, "customer_code"), "Customer"), (col(cu, "segment_name"), "Segment"),
                        (meas("fact_sales", "Top 10 Revenue"), "Revenue"), (meas("fact_sales", "Total Orders"), "Orders")]},
            "Top 10 customers by revenue", table_fmt(),
            sort=(meas("fact_sales", "Top 10 Revenue"), "Descending"))
    y3 = y2 + h2 + G
    h3 = H - y3 - M
    p.chart("spend_segment", a, y3, aw, h3, "clusteredBarChart",
            {"Category": [(col(cu, "segment_name"), "Segment")], "Y": [(meas("fact_sales", "Avg Spend (Rp ribu)"), "Avg spend")]},
            "Average spending per customer by segment (Rp ribu)", bars(fill_measure=(cu, "Segment Color")),
            sort=(meas("fact_sales", "Avg Spend (Rp ribu)"), "Descending"), tooltip_page=TOOLTIP)
    p.chart("aov_segment", b, y3, bw, h3, "clusteredBarChart",
            {"Category": [(col(cu, "segment_name"), "Segment")], "Y": [(meas("fact_sales", "AOV (Rp ribu)"), "AOV")]},
            "Average order value by segment (Rp ribu)", bars(fill_measure=(cu, "Segment Color")),
            sort=(meas("fact_sales", "AOV (Rp ribu)"), "Descending"), tooltip_page=TOOLTIP)
    p.chart("clv_tier", c, y3, cw, h3, "clusteredBarChart",
            {"Category": [(col(cu, "clv_tier"), "Predicted CLV tier")], "Y": [(meas("dim_customer", "Historical CLV (Rp ribu)"), "Avg historical CLV")]},
            "Avg historical CLV by predicted-CLV tier (Rp ribu)", bars(VIOLET), sort=(col(cu, "clv_tier"), "Ascending"))
    return p


def page_retention() -> Page:
    p = Page("retention_churn", "4 · Customer Retention & Churn",
             "3-month retention = customers of period P-1 buying again in P · churn (inactivity) = no purchase for more than T days (P90 of purchase gaps)")
    y = HEADER_H + 12
    p.slicers(y, [("sl_segment", col("dim_customer", "segment_name"), "Customer segment"),
                  ("sl_region", col("dim_location", "region"), "Region"),
                  ("sl_cohort", col("dim_customer", "cohort"), "Acquisition cohort")])
    y1 = y + SLICER_H + G
    p.kpis(y1, [
        ("kpi_ret", meas("period_retention", "Retention Rate"), "Retention rate (3-month)", BLUE),
        ("kpi_churn", meas("period_retention", "Churn Rate"), "Churn rate (3-month)", RED),
        ("kpi_repeat", meas("dim_customer", "Repeat Purchase Rate"), "Repeat purchase rate", AQUA),
        ("kpi_react", meas("period_retention", "Reactivated Customers"), "Reactivated customers", VIOLET),
        ("kpi_inactive", meas("dim_customer", "Churn Rate (Inactivity)"), "Inactive > T days (churned)", ORANGE),
        ("kpi_active", meas("dim_customer", "Active Customers"), "Active customers", GREEN),
    ])
    y2 = y1 + 78 + G
    hw = 790
    h2 = H - y2 - M
    cr = "cohort_retention"
    p.chart("cohort_heatmap", M, y2, hw, h2, "pivotTable",
            {"Rows": [(col(cr, "cohort"), "Cohort")], "Columns": [(col(cr, "month_index"), "Months since first purchase")],
             "Values": [(meas(cr, "Cohort Retention"), "Retention")]},
            "Cohort retention heatmap · % of cohort buying again k months after the first purchase",
            {"columnHeaders": [{"properties": {"fontColor": color(INK2), "backColor": color(TABLE_HEAD), "fontSize": lit(8)}}],
             "rowHeaders": [{"properties": {"fontColor": color(INK2), "fontSize": lit(8)}}],
             "values": [{"properties": {"fontSize": lit(7)}},
                        {"properties": {"backColor": color_by(cr, "Cohort Cell Color"),
                                        "fontColor": color_by(cr, "Cohort Text Color")},
                         "selector": {**WILDCARD, "metadata": f"{cr}.Cohort Retention"}}],
             "subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}],
             "grid": [{"properties": {"gridVertical": lit(True), "gridVerticalColor": color("#ffffff"),
                                      "gridHorizontalColor": color("#ffffff"), "rowPadding": lit(1)}}]})
    rx = M + hw + G
    rw = W - M - rx
    hh = (h2 - 2 * G) // 3
    p.chart("churn_segment", rx, y2, rw, hh, "clusteredBarChart",
            {"Category": [(col("dim_customer", "segment_name"), "Segment")],
             "Y": [(meas("dim_customer", "Churn Rate (Inactivity)"), "Churned share")]},
            "Churn (inactive > T) by segment", bars(fill_measure=("dim_customer", "Segment Color")),
            sort=(meas("dim_customer", "Churn Rate (Inactivity)"), "Descending"), tooltip_page=TOOLTIP)
    inact = axis_fmt()
    inact["dataPoint"] = [{"properties": {"fill": color(BLUE)}}]
    inact["labels"] = [{"properties": {"show": lit(True), "color": color(INK2), "fontSize": lit(8), "labelDisplayUnits": lit(1)}}]
    p.chart("inactivity", rx, y2 + hh + G, rw, hh, "columnChart",
            {"Category": [(col("dim_customer", "inactivity_band"), "Days since last purchase")],
             "Y": [(meas("dim_customer", "Customers (Snapshot)"), "Customers")]},
            "Days since last purchase (customers)", inact, sort=(col("dim_customer", "inactivity_band"), "Ascending"))
    rt = lines({"period_retention.Retention Rate": BLUE, "period_retention.Reactivation Rate": ORANGE}, markers=True)
    p.chart("retention_trend", rx, y2 + 2 * (hh + G), rw, h2 - 2 * (hh + G), "lineChart",
            {"Category": [(col("period_retention", "period"), "Period")],
             "Y": [(meas("period_retention", "Retention Rate"), "Retention"),
                   (meas("period_retention", "Reactivation Rate"), "Reactivation")]},
            "Retention & reactivation trend (3-month periods)", rt)
    return p


def page_behavior() -> Page:
    p = Page("purchasing_behavior", "5 · Customer Purchasing Behavior",
             "When, what and how customers buy · product affinity = category association rules (support / confidence / lift)")
    y = HEADER_H + 12
    global_slicers(p, y)
    y1 = y + SLICER_H + G
    p.kpis(y1, [
        ("kpi_freq", meas("fact_sales", "Purchase Frequency"), "Purchase frequency", BLUE),
        ("kpi_interval", meas("dim_customer", "Average Purchase Interval"), "Avg purchase interval (repeaters)", VIOLET),
        ("kpi_basket", meas("fact_sales", "Average Basket Size"), "Average basket size (items)", AQUA),
        ("kpi_aov", meas("fact_sales", "Average Order Value"), "Average order value", GREEN),
        ("kpi_inst", meas("fact_orders", "Average Installments"), "Avg installments", ORANGE),
        ("kpi_review", meas("fact_orders", "Average Review Score"), "Avg review score", MAGENTA),
    ])
    y2, h2 = y1 + 78 + G, 225
    (a, aw), (b, bw), (c, cw) = grid_cols(3)
    p.chart("orders_month", a, y2, aw, h2, "lineChart",
            {"Category": [(col("dim_date", "month_start"), "Month")], "Y": [(meas("fact_sales", "Purchase Frequency"), "Orders per customer")]},
            "Orders per customer (monthly)", lines({"fact_sales.Purchase Frequency": BLUE}))
    col_ = axis_fmt()
    col_["dataPoint"] = [{"properties": {"fill": color(BLUE)}}]
    col_.update(legend(False))
    p.chart("dow", b, y2, bw, h2, "columnChart",
            {"Category": [(col("dim_date", "day_name"), "Day")], "Y": [(meas("fact_orders", "Orders"), "Orders")]},
            "Orders by day of week", col_)
    p.chart("hour", c, y2, cw, h2, "columnChart",
            {"Category": [(col("fact_orders", "purchase_hour"), "Hour")], "Y": [(meas("fact_orders", "Orders"), "Orders")]},
            "Orders by hour of day", col_)
    y3 = y2 + h2 + G
    h3 = H - y3 - M
    lw = 320
    p.chart("category_pref", M, y3, lw, h3, "clusteredBarChart",
            {"Category": [(col("dim_product", "category_group"), "Category group")], "Y": [(meas("fact_sales", "Revenue (Rp miliar)"), "Revenue")]},
            "Revenue by category (Rp miliar)", bars(BLUE), sort=(meas("fact_sales", "Revenue (Rp miliar)"), "Descending"))
    pa = "product_affinity"
    mx = M + lw + G
    mw_ = 380
    p.chart("affinity", mx, y3, mw_, h3, "tableEx",
            {"Values": [(col(pa, "antecedent"), "If bought"), (col(pa, "consequent"), "Then also"),
                        (agg(pa, "support_count", "max"), "Baskets"), (agg(pa, "lift", "max"), "Lift")]},
            "Cross-selling rules (lift > 1)", table_fmt(),
            sort=(agg(pa, "lift", "max"), "Descending"))
    cs = "category_by_segment"
    cx = mx + mw_ + G
    p.chart("cross_sell", cx, y3, W - M - cx, h3, "pivotTable",
            {"Rows": [(col(cs, "category_group"), "Category")], "Columns": [(col(cs, "segment_name"), "Segment")],
             "Values": [(agg(cs, "orders"), "Orders")]},
            "Orders per category × segment",
            {"columnHeaders": [{"properties": {"fontColor": color(INK2), "backColor": color(TABLE_HEAD), "fontSize": lit(8),
                                               "wordWrap": lit(True)}}],
             "rowHeaders": [{"properties": {"fontColor": color(INK2), "fontSize": lit(8)}}],
             "values": [{"properties": {"fontSize": lit(8)}}],
             "subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]})
    return p


def page_strategy() -> Page:
    p = Page("marketing_strategy", "6 · Marketing & Business Strategy",
             "Where to act: segment opportunity, high-value customers about to lapse, high-potential customers, recommended campaigns")
    y1 = HEADER_H + 12
    p.kpis(y1, [
        ("kpi_hvar", meas("dim_customer", "High-Value At-Risk Customers"), "High-value at-risk customers", ORANGE),
        ("kpi_hvar_rev", meas("dim_customer", "High-Value At-Risk Revenue"), "Their historical revenue", ORANGE),
        ("kpi_hp", meas("dim_customer", "High-Potential Customers"), "High-potential customers (top 5% pred. CLV)", VIOLET),
        ("kpi_hp_clv", meas("dim_customer", "High-Potential CLV"), "Their predicted 12-month revenue", VIOLET),
    ])
    y2, h2 = y1 + 78 + G, 250
    (a, aw), (b, bw), (c, cw) = grid_cols(3)
    sp = "segment_profile"
    p.chart("opportunity", a, y2, aw, h2, "scatterChart",
            {"Category": [(col(sp, "segment_name"), "Segment")],
             "X": [(agg(sp, "customer_share", "max"), "% of customers")],
             "Y": [(agg(sp, "avg_monetary", "max"), "Avg spend (Rp)")],
             "Size": [(agg(sp, "revenue", "max"), "Revenue")]},
            "Opportunity · reach (x) vs spend (y)",
            scatter_fmt((sp, "Profile Color")))
    cu = "dim_customer"
    tw = {"customer_code": 70}
    p.chart("hvar", b, y2, bw, h2, "tableEx",
            {"Values": [(col(cu, "customer_code"), "Customer"), (col(cu, "segment_name"), "Segment"),
                        (meas(cu, "High-Value At-Risk Revenue"), "Revenue"),
                        (agg(cu, "recency_days", "max"), "Days inactive")]},
            "High-value customers about to lapse", table_fmt(),
            sort=(meas(cu, "High-Value At-Risk Revenue"), "Descending"))
    p.chart("hipot", c, y2, cw, h2, "tableEx",
            {"Values": [(col(cu, "customer_code"), "Customer"), (col(cu, "segment_name"), "Segment"),
                        (meas(cu, "High-Potential CLV"), "Pred. CLV 12m"),
                        (agg(cu, "frequency", "max"), "Orders")]},
            "High-potential customers (top 5% pred. CLV)", table_fmt(),
            sort=(meas(cu, "High-Potential CLV"), "Descending"))
    y3 = y2 + h2 + G
    h3 = H - y3 - M - 40
    gw = 360
    p.chart("growth", M, y3, gw, h3, "clusteredBarChart",
            {"Category": [(col(sp, "segment_name"), "Segment")], "Y": [(agg(sp, "segment_growth_rate", "max"), "Growth")]},
            "Segment size change vs 6 months earlier",
            bars(fill_measure=(sp, "Profile Color")), sort=(agg(sp, "segment_growth_rate", "max"), "Descending"))
    sx = M + gw + G
    p.chart("strategy", sx, y3, W - M - sx, h3, "tableEx",
            {"Values": [(col(sp, "segment_name"), "Segment"), (agg(sp, "customers", "max"), "Customers"),
                        (agg(sp, "revenue_contribution", "max"), "% revenue"),
                        (col(sp, "recommended_strategy"), "Recommended campaign strategy")]},
            "Recommended campaign strategy per segment",
            table_fmt({"segment_profile.segment_name": 110, "Max(segment_profile.customers)": 80,
                       "Max(segment_profile.revenue_contribution)": 76,
                       "segment_profile.recommended_strategy": W - M - sx - 110 - 80 - 76 - 60}, table=True, wrap=True),
            sort=(agg(sp, "revenue_contribution", "max"), "Descending"))
    p.card("campaign_note", M, H - M - 34, W - 2 * M, 34, meas("meta", "Campaign Note"), None, size=9,
           value_color=INK2, show_label=False)
    return p


def page_details() -> Page:
    p = Page("customer_details", "Customer Details (drill-through)",
             "Customers of the selected segment · reached by right-click → Drill through on any segment visual")
    p.drillthrough_on(col("dim_customer", "segment_name"))
    y1 = HEADER_H + 12
    p.kpis(y1, [
        ("kpi_cust", meas("dim_customer", "Customers (Snapshot)"), "Customers", BLUE),
        ("kpi_rev", meas("fact_sales", "Revenue Label"), "Revenue", GREEN),
        ("kpi_aov", meas("fact_sales", "Average Order Value"), "AOV", ORANGE),
        ("kpi_repeat", meas("dim_customer", "Repeat Purchase Rate"), "Repeat rate", AQUA),
        ("kpi_churn", meas("dim_customer", "Churn Rate (Inactivity)"), "Inactive > T", RED),
        ("kpi_pclv", meas("dim_customer", "Predicted CLV 12m"), "Avg predicted CLV", VIOLET),
    ])
    y2 = y1 + 78 + G
    h2 = H - y2 - M
    tw = 860
    cu = "dim_customer"
    p.chart("customers", M, y2, tw, h2, "tableEx",
            {"Values": [(col(cu, "customer_code"), "Customer"), (col(cu, "segment_name"), "Segment"),
                        (agg(cu, "recency_days", "max"), "Recency (d)"), (agg(cu, "frequency", "max"), "Orders"),
                        (agg(cu, "monetary", "max"), "Revenue (Rp)"), (agg(cu, "predicted_clv_12m", "max"), "Pred. CLV 12m"),
                        (col(cu, "top_category_group"), "Top category"), (col(cu, "churn_status"), "Status")]},
            "Customer list (sorted by revenue)", table_fmt(), sort=(agg(cu, "monetary", "max"), "Descending"))
    rx = M + tw + G
    p.chart("by_state", rx, y2, W - M - rx, h2, "clusteredBarChart",
            {"Category": [(col("dim_location", "state"), "State")], "Y": [(meas(cu, "Customers (Snapshot)"), "Customers")]},
            "Where they live (state)", bars(BLUE), sort=(meas(cu, "Customers (Snapshot)"), "Descending"))
    return p


def page_tooltip() -> Page:
    tw, th = 340, 230
    p = Page(TOOLTIP, "Segment tooltip", "", size=(tw, th), header=False)
    p.tooltip_on(col("dim_customer", "segment_name"))
    p.card("tt_name", 8, 6, tw - 16, 40, col("dim_customer", "segment_name"), None, size=13, show_label=False)
    items = [("tt_cust", meas("dim_customer", "Customers (Snapshot)"), "Customers"),
             ("tt_contrib", meas("fact_sales", "Revenue Contribution"), "% of revenue"),
             ("tt_aov", meas("fact_sales", "Average Order Value"), "AOV"),
             ("tt_churn", meas("dim_customer", "Churn Rate (Inactivity)"), "Inactive > T")]
    for i, (n, f, lab) in enumerate(items):
        x = 8 + (i % 2) * ((tw - 24) // 2 + 8)
        y = 52 + (i // 2) * 86
        p.card(n, x, y, (tw - 24) // 2, 78, id_label(f), lab, size=16)
    return p


def page_appendix() -> Page:
    p = Page("appendix_models_kpis", "Appendix · Model comparison & KPI dictionary",
             "Why this segmentation was selected (PRD 5.4) and how every KPI is defined (PRD 8.6)")
    y1 = HEADER_H + 12
    h1 = 260
    mc = "model_comparison"
    p.chart("models", M, y1, W - 2 * M, h1, "tableEx",
            {"Values": [(col(mc, "run_id"), "Finalist"), (col(mc, "algorithm"), "Algorithm"), (agg(mc, "k", "max"), "K"),
                        (agg(mc, "silhouette", "max"), "Silhouette (avg of 7 spaces)"),
                        (agg(mc, "davies_bouldin", "max"), "Davies-Bouldin"),
                        (agg(mc, "stability_bootstrap_ari", "max"), "Stability (bootstrap ARI)"),
                        (agg(mc, "size_entropy", "max"), "Size balance"),
                        (agg(mc, "interpretability", "max"), "Interpretability"),
                        (agg(mc, "composite", "max"), "Composite score")]},
            "Model comparison · composite = 15% silhouette, 10% DB, 5% CH, 25% stability, 15% balance, 30% interpretability",
            table_fmt(), sort=(agg(mc, "composite", "max"), "Descending"))
    y2 = y1 + h1 + G
    kd = "kpi_dictionary"
    p.chart("kpis", M, y2, W - 2 * M, H - y2 - M, "tableEx",
            {"Values": [(col(kd, "category"), "Category"), (col(kd, "kpi"), "KPI"),
                        (col(kd, "business_definition"), "Definition"), (col(kd, "formula"), "Formula"),
                        (col(kd, "baseline_display"), "Baseline"), (col(kd, "target_display"), "Target"),
                        (col(kd, "target_basis"), "Target basis"), (col(kd, "business_owner"), "Owner")]},
            "KPI dictionary", table_fmt(wrap=True))
    return p


# ============================================================================================ report
def build_report(pages: list[Page]) -> None:
    dump(RP / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                  "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    d = RP / "definition"
    dump(d / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
                              "version": "2.0.0"})
    theme = BASE_THEME if (PBI_THEMES / f"{BASE_THEME}.json").exists() else \
        sorted(p.stem for p in PBI_THEMES.glob("*.json"))[-1]
    at_import = {"visual": V_VISUAL, "report": V_REPORT, "page": V_PAGE}
    dump(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/{V_REPORT}/schema.json",
        "themeCollection": {"baseTheme": {"name": theme, "reportVersionAtImport": at_import, "type": "SharedResources"}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": theme, "path": f"BaseThemes/{theme}.json", "type": "BaseTheme"}]}],
        "objects": {"outspacePane": [{"properties": {"expanded": lit(False)}}]},   # filter pane collapsed
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
    })
    dump(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                      "pageOrder": [p.name for p in pages], "activePageName": pages[0].name})
    for p in pages:
        p.write(d)
    sr = RP / "StaticResources" / "SharedResources" / "BaseThemes"
    sr.mkdir(parents=True, exist_ok=True)
    if (PBI_THEMES / f"{theme}.json").exists():
        shutil.copy(PBI_THEMES / f"{theme}.json", sr / f"{theme}.json")


ALL_PAGES = [page_executive, page_segmentation, page_value, page_retention, page_behavior, page_strategy,
             page_details, page_tooltip, page_appendix]


def main(active: str | None = None, only: bool = False) -> None:
    for p in (SM, RP):
        if p.exists():
            shutil.rmtree(p)
    db.wait_ready()
    _guid_counter[0] = 0
    pages = [f() for f in ALL_PAGES]       # pages first: they register the Indonesian label measures
    build_semantic_model()
    order = [p.name for p in pages]
    if active:
        pages.sort(key=lambda p: p.name != active)
        if only:
            keep = {active, TOOLTIP, "customer_details"}
            pages = [p for p in pages if p.name in keep]
    build_report(pages)
    if active and not only:
        dump(RP / "definition" / "pages" / "pages.json",
             {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
              "pageOrder": order, "activePageName": active})
    dump(OUT / f"{NAME}.pbip", {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                "settings": {"enableAutoRecovery": False}})
    write(OUT / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    n_vis = sum(len(p.visuals) for p in pages)
    print(f"[pbip] {OUT / (NAME + '.pbip')}  ({len(pages)} pages, {n_vis} visuals, {len(TABLES)} DirectQuery tables, "
          f"{len(RELATIONSHIPS)} relationships, {len(MEASURES)} measures)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else None, only="--only" in sys.argv)

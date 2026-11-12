"""PostgreSQL helpers: engine, SQL-file execution, fast DataFrame load via COPY."""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from custseg import config

_ENGINE: Engine | None = None


def engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(config.DB_URL, pool_pre_ping=True)
    return _ENGINE


def wait_ready(timeout: float = 60) -> None:
    t0 = time.time()
    while True:
        try:
            with engine().connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception:  # noqa: BLE001
            if time.time() - t0 > timeout:
                raise SystemExit("PostgreSQL not reachable on port 5435 - run `docker compose up -d db` first")
            time.sleep(2)


def sql_params() -> dict[str, str]:
    """Values substituted into {{PLACEHOLDER}}s so SQL and Python share one configuration."""
    return {"WINDOW_START": config.WINDOW_START, "WINDOW_END": config.WINDOW_END,
            "ANALYSIS_DATE": config.ANALYSIS_DATE,
            "REVENUE_STATUSES": ", ".join(f"'{s}'" for s in config.REVENUE_STATUSES)}


def run_sql_file(path: Path, extra: dict[str, str] | None = None) -> None:
    sql = path.read_text(encoding="utf-8")
    for k, v in {**sql_params(), **(extra or {})}.items():
        sql = sql.replace("{{" + k + "}}", v)
    raw = engine().raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)
        raw.commit()
    finally:
        raw.close()


def query(sql: str, **params) -> pd.DataFrame:
    with engine().connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def execute(sql: str) -> None:
    with engine().begin() as c:
        c.execute(text(sql))


PG_TYPES = {"int64": "BIGINT", "int32": "INTEGER", "float64": "DOUBLE PRECISION", "float32": "DOUBLE PRECISION",
            "bool": "BOOLEAN", "object": "TEXT", "string": "TEXT", "category": "TEXT",
            "datetime64[ns]": "TIMESTAMP", "datetime64[us]": "TIMESTAMP", "Int64": "BIGINT", "boolean": "BOOLEAN"}


def load_df(df: pd.DataFrame, table: str, schema: str = "mart", all_text: bool = False,
            primary_key: str | None = None) -> None:
    """(Re)create schema.table from a DataFrame and bulk-load it with COPY."""
    cols = []
    for c, dt in df.dtypes.items():
        pgt = "TEXT" if all_text else PG_TYPES.get(str(dt), "TEXT")
        cols.append(f'"{c}" {pgt}')
    if primary_key:
        cols.append(f'PRIMARY KEY ("{primary_key}")')
    raw = engine().raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            cur.execute(f'DROP TABLE IF EXISTS {schema}."{table}" CASCADE')
            cur.execute(f'CREATE TABLE {schema}."{table}" ({", ".join(cols)})')
            buf = io.StringIO()
            df.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            cur.copy_expert(f'COPY {schema}."{table}" FROM STDIN WITH (FORMAT csv, NULL \'\\N\')', buf)
        raw.commit()
    finally:
        raw.close()

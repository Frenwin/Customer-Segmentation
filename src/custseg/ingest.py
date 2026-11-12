"""Layer 1 - Raw: load the Olist CSV files *as-is* (every column TEXT) into schema `raw`.

No cleaning happens here: types, nulls, duplicates are all handled in the staging layer, so the raw tables are an
exact, re-loadable copy of the source files. A SHA-256 per file is stored as the dataset version.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone

from custseg import config, db


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw() -> dict:
    db.wait_ready()
    db.execute("DROP SCHEMA IF EXISTS raw CASCADE; CREATE SCHEMA raw;")
    manifest = {"dataset": config.DATASET_NAME, "url": config.DATASET_URL, "license": config.DATASET_LICENSE,
                "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {}}
    raw = db.engine().raw_connection()
    try:
        for table, fname in config.RAW_FILES.items():
            path = config.RAW_DIR / fname
            if not path.exists():
                raise SystemExit(f"missing {path} - see 02_data/README.md for the download command")
            with open(path, encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f))
            cols = ", ".join(f'"{c}" TEXT' for c in header)
            with raw.cursor() as cur:
                cur.execute(f"CREATE TABLE raw.{table} ({cols})")
                with open(path, encoding="utf-8-sig", newline="") as f:
                    cur.copy_expert(f"COPY raw.{table} FROM STDIN WITH (FORMAT csv, HEADER true)", f)
                cur.execute(f"SELECT COUNT(*) FROM raw.{table}")
                n = cur.fetchone()[0]
            raw.commit()
            manifest["files"][table] = {"file": fname, "rows": n, "columns": header, "bytes": path.stat().st_size,
                                        "sha256": sha256(path)}
            print(f"[raw] raw.{table:<22} {n:>9,} rows")
    finally:
        raw.close()
    combined = hashlib.sha256("".join(v["sha256"] for v in manifest["files"].values()).encode()).hexdigest()
    manifest["dataset_version"] = combined[:12]
    out = config.ROOT / "02_data" / "dataset_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    load_raw()

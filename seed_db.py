import os
import sys
from pathlib import Path
import pandas as pd

from db_access import init_db_schema, count_devices, bulk_upsert_devices_from_dataframe


def main() -> int:
    init_db_schema()

    existing = count_devices()
    if existing > 0:
        print(f"[seed_db] devices already present: {existing}. Skipping seed.")
        return 0

    base_dir = Path(__file__).resolve().parent
    default_seed_xlsx = base_dir / "seed" / "devicepassport_catalog.xlsx"
    seed_xlsx = os.getenv("DP_SEED_XLSX", str(default_seed_xlsx))
    seed_sheet = os.getenv("DP_SEED_SHEET", "devices")

    if not os.path.exists(seed_xlsx):
        print(f"[seed_db] ERROR: seed workbook not found at {seed_xlsx}")
        return 2

    print(f"[seed_db] Seeding DB from: {seed_xlsx} (sheet={seed_sheet})")
    df = pd.read_excel(seed_xlsx, sheet_name=seed_sheet)

    if df.empty:
        print("[seed_db] ERROR: seed sheet is empty.")
        return 3

    required_cols = {"device_id"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"[seed_db] ERROR: missing required columns in seed sheet: {sorted(missing)}")
        return 4

    inserted = bulk_upsert_devices_from_dataframe(df)
    after = count_devices()
    print(f"[seed_db] Seed complete. Upserted rows: {inserted}. Devices now in DB: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

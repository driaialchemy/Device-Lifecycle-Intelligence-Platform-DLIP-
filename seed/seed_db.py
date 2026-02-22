from __future__ import annotations
import os
import pandas as pd

from db_access import init_db_schema, bulk_upsert_devices_from_dataframe, replace_sensor_timeseries, replace_battery_history, count_devices

def main() -> int:
    init_db_schema()
    seed_xlsx = os.getenv("DP_SEED_XLSX", "/app/seed/devicepassport_catalog.xlsx")

    df_devices = pd.read_excel(seed_xlsx, sheet_name="devices")
    df_sensor = pd.read_excel(seed_xlsx, sheet_name="sensor_timeseries")
    df_battery = pd.read_excel(seed_xlsx, sheet_name="battery_history")

    up = bulk_upsert_devices_from_dataframe(df_devices)
    ns = replace_sensor_timeseries(df_sensor)
    nb = replace_battery_history(df_battery)

    print(f"[seed_db] devices_upserted={up} devices_in_db={count_devices()} sensor_rows={ns} battery_rows={nb}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

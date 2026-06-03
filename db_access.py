import os
import json
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, RealDictCursor

# Load local .env for Windows/local runs.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

# Prefer the documented env var, but keep the older Docker name as a fallback.
DB_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("DP_DATABASE_URL")
    or "postgresql://postgres:postgres@localhost:5434/devicepassport"
)


def get_conn():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(DB_URL)


def connect():
    """Backward-compatible alias used by older persistence helpers."""
    return get_conn()


def init_db_schema() -> None:
    """Create required tables/indexes if they do not exist (non-destructive)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS device_registry (
                    device_id VARCHAR(50) PRIMARY KEY,
                    device_payload JSONB
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id VARCHAR(50) PRIMARY KEY,
                    device_id VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    run_id VARCHAR(50),
                    event_type VARCHAR(50),
                    payload_json JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )

            # Keep backward compatibility with db_persist.persist_run(...).
            cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS trace_id TEXT;")
            cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_type TEXT;")
            cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS release_version TEXT;")

            # Minimal helpful indexes.
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_device_created ON runs (device_id, created_at DESC);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_log_run_id_id ON audit_log (run_id, id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);"
            )
        conn.commit()


def list_devices(limit: int | None = None) -> list[dict[str, Any]]:
    """Return device rows as dictionaries, with optional LIMIT."""
    query = "SELECT device_id, device_payload FROM device_registry ORDER BY device_id DESC"
    params: tuple[Any, ...] = ()

    if limit is not None:
        safe_limit = max(int(limit), 1)
        query += " LIMIT %s"
        params = (safe_limit,)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = [dict(row) for row in cur.fetchall()]

    for row in rows:
        row["device_payload"] = _normalize_device_payload(row.get("device_payload"))
    return rows


def get_device_payload(did: str) -> dict[str, Any]:
    """Return one device payload or an empty dict if missing."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT device_payload FROM device_registry WHERE device_id = %s",
                (did,),
            )
            row = cur.fetchone()

    if not row:
        return {}
    payload = row.get("device_payload")
    normalized = _normalize_device_payload(payload if isinstance(payload, dict) else (payload or {}))
    normalized.setdefault("device_id", did)
    return normalized


def _normalize_device_payload(payload: Any) -> dict[str, Any]:
    """Normalize seed workbook payload fields into the app's expected shape."""
    if not isinstance(payload, dict):
        return {}

    normalized = dict(payload)
    json_field_map = {
        "gdpr_flags_json": "gdpr_flags",
        "r2v3_flags_json": "r2v3_flags",
        "audit_trail_json": "audit_trail",
    }

    for source_key, target_key in json_field_map.items():
        if target_key in normalized or source_key not in normalized:
            continue
        raw_value = normalized.get(source_key)
        if isinstance(raw_value, str):
            try:
                normalized[target_key] = json.loads(raw_value)
            except json.JSONDecodeError:
                normalized[target_key] = {}
        elif isinstance(raw_value, dict):
            normalized[target_key] = raw_value

    return normalized


def fetch_runs_for_device(did: str) -> pd.DataFrame:
    """Return runs for a device, newest-first."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT run_id, device_id, created_at
                FROM runs
                WHERE device_id = %s
                ORDER BY created_at DESC, run_id DESC
                """,
                (did,),
            )
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def fetch_audit_chain(rid: str) -> pd.DataFrame:
    """Return audit chain events for a run, ordered by event sequence."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, run_id, event_type, payload_json, created_at
                FROM audit_log
                WHERE run_id = %s
                ORDER BY id ASC
                """,
                (rid,),
            )
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def fetch_audit_events(limit: int = 200) -> pd.DataFrame:
    """Return recent audit log events, newest-first."""
    safe_limit = max(int(limit), 1)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, run_id, event_type, payload_json, created_at
                FROM audit_log
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def fetch_recent_runs_with_event_counts(limit: int = 50) -> pd.DataFrame:
    """Return recent runs enriched with structured audit event counts."""
    safe_limit = max(int(limit), 1)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    r.run_id,
                    r.device_id,
                    r.created_at,
                    COUNT(a.id)::int AS audit_events,
                    MAX(a.created_at) AS latest_event_at
                FROM runs r
                LEFT JOIN audit_log a ON a.run_id = r.run_id
                GROUP BY r.run_id, r.device_id, r.created_at
                ORDER BY r.created_at DESC, r.run_id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def count_devices() -> int:
    """Return total number of devices in registry."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM device_registry")
            row = cur.fetchone()
    return int(row[0] if row else 0)


def bulk_upsert_devices_from_dataframe(df: pd.DataFrame) -> int:
    """Upsert device rows from a DataFrame into device_registry."""
    if df is None or df.empty:
        return 0
    if "device_id" not in df.columns:
        raise ValueError("DataFrame must include a 'device_id' column")

    normalized_df = df.where(pd.notna(df), None)
    upsert_rows: list[tuple[str, Json]] = []

    for row in normalized_df.to_dict(orient="records"):
        device_id = row.get("device_id")
        if device_id is None:
            continue
        device_id = str(device_id).strip()
        if not device_id:
            continue

        payload: Any = row.get("device_payload")
        if payload is None:
            payload = {
                k: v
                for k, v in row.items()
                if k not in {"device_id", "device_payload"} and v is not None
            }
        elif isinstance(payload, str):
            payload = payload.strip()
            if not payload:
                payload = {}
            else:
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"device_payload": payload}

        if not isinstance(payload, dict):
            payload = {"device_payload": payload}

        upsert_rows.append((device_id, Json(payload)))

    if not upsert_rows:
        return 0

    query = """
        INSERT INTO device_registry (device_id, device_payload)
        VALUES (%s, %s)
        ON CONFLICT (device_id)
        DO UPDATE SET device_payload = EXCLUDED.device_payload
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            for params in upsert_rows:
                cur.execute(query, params)
        conn.commit()

    return len(upsert_rows)


def fetch_recent_runs(limit: int = 10) -> pd.DataFrame:
    """Return recent runs, newest-first."""
    safe_limit = max(int(limit), 1)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT run_id, device_id, created_at
                FROM runs
                ORDER BY created_at DESC, run_id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def compute_arbiter_risk_distribution(days: int = 30) -> pd.DataFrame:
    """Aggregate arbiter risk ratings from recent audit_log payload_json values."""
    safe_days = max(int(days), 0)

    query = """
    WITH recent AS (
        SELECT
            run_id,
            event_type,
            created_at,
            COALESCE(
                NULLIF(payload_json->>'arbiter_risk_rating', ''),
                NULLIF(payload_json#>>'{final_consensus,arbiter_risk_rating}', ''),
                NULLIF(payload_json#>>'{final,arbiter_risk_rating}', ''),
                NULLIF(payload_json#>>'{arbiter,risk_rating}', ''),
                NULLIF(payload_json#>>'{details,arb,risk_rating}', ''),
                NULLIF(payload_json->>'risk_rating', '')
            ) AS arbiter_risk_rating
        FROM audit_log
        WHERE created_at >= NOW() - make_interval(days => %s)
    ),
    ranked AS (
        SELECT
            run_id,
            arbiter_risk_rating,
            ROW_NUMBER() OVER (
                PARTITION BY run_id
                ORDER BY
                    CASE event_type
                        WHEN 'FINAL' THEN 0
                        WHEN 'ARBITER' THEN 1
                        ELSE 2
                    END,
                    created_at DESC
            ) AS rn
        FROM recent
        WHERE arbiter_risk_rating IS NOT NULL
    )
    SELECT arbiter_risk_rating, COUNT(*)::int AS count
    FROM ranked
    WHERE rn = 1
    GROUP BY arbiter_risk_rating
    ORDER BY count DESC, arbiter_risk_rating ASC;
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (safe_days,))
            rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=["arbiter_risk_rating", "count"])

    df = pd.DataFrame(rows)
    return df[["arbiter_risk_rating", "count"]]

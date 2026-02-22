from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from psycopg2.extras import Json

from db_access import connect


def _canon(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def persist_run(run_id: str, device_id: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (run_id, device_id) VALUES (%s,%s) ON CONFLICT (run_id) DO NOTHING;",
                (run_id, device_id),
            )
        conn.commit()


def persist_agent_output(run_id: str, device_id: str, out: Dict[str, Any]) -> None:
    sql = '''
    INSERT INTO agent_outputs (
      run_id, device_id, agent_name, domain, round, stance, text, risk_rating, uncertainty, tool_outputs
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    '''
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id,
                    device_id,
                    str(out.get("agent", "")),
                    str(out.get("domain", "")),
                    int(out.get("round", 0)),
                    out.get("stance"),
                    str(out.get("text", "")),
                    out.get("risk_rating"),
                    float(out.get("uncertainty", 0.0)) if out.get("uncertainty") is not None else None,
                    Json(out.get("tool_outputs") or {}),
                ),
            )
        conn.commit()


def persist_tool_event(
    run_id: str,
    device_id: str,
    event_type: str,
    tool_name: str,
    tool_version: str,
    input_data_ref: str,
    metrics_json: Dict[str, Any],
    warnings_json: Optional[Dict[str, Any]] = None,
    confidence: Optional[float] = None,
) -> str:
    artifact_hash = _sha(_canon(metrics_json or {}))
    sql = '''
    INSERT INTO tool_events (
      run_id, device_id, event_type, tool_name, tool_version,
      artifact_hash, input_data_ref, metrics_json, warnings_json, confidence
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    '''
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id,
                    device_id,
                    event_type,
                    tool_name,
                    tool_version,
                    artifact_hash,
                    input_data_ref,
                    Json(metrics_json or {}),
                    Json(warnings_json or {}),
                    confidence,
                ),
            )
        conn.commit()
    return artifact_hash


def append_audit_chain(run_id: str, device_id: str, event_type: str, payload_json: Dict[str, Any]) -> str:
    prev_hash = None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_hash FROM audit_chain WHERE run_id=%s ORDER BY id DESC LIMIT 1;",
                (run_id,),
            )
            row = cur.fetchone()
            if row:
                prev_hash = row[0]

    base = f"{prev_hash or ''}|{event_type}|{_canon(payload_json)}"
    event_hash = _sha(base)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_chain (run_id, device_id, event_type, payload_json, prev_hash, event_hash) VALUES (%s,%s,%s,%s,%s,%s);",
                (run_id, device_id, event_type, Json(payload_json), prev_hash, event_hash),
            )
        conn.commit()

    return event_hash

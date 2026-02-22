from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, List, Tuple

from psycopg2.extras import Json, RealDictCursor

from db_access import connect


def _canon(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def persist_run(
    run_id: str,
    device_id: str,
    trace_id: Optional[str] = None,
    run_type: Optional[str] = None,
    release_version: Optional[str] = None,
) -> None:
    """
    Backward-compatible run persistence.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (run_id, device_id, trace_id, run_type, release_version)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO UPDATE
                SET device_id = EXCLUDED.device_id,
                    trace_id = COALESCE(EXCLUDED.trace_id, runs.trace_id),
                    run_type = COALESCE(EXCLUDED.run_type, runs.run_type),
                    release_version = COALESCE(EXCLUDED.release_version, runs.release_version);
                """,
                (run_id, device_id, trace_id, run_type, release_version),
            )
        conn.commit()


def persist_agent_output(
    run_id: str,
    device_id: str,
    out: Dict[str, Any],
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    prompt_hash: Optional[str] = None,
) -> None:
    sql = """
    INSERT INTO agent_outputs (
      run_id, device_id, agent_name, domain, round, stance, text, risk_rating, uncertainty, tool_outputs,
      llm_provider, llm_model, prompt_hash
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    """
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
                    llm_provider,
                    llm_model,
                    prompt_hash,
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
    status: Optional[str] = "success",
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    runtime_ms: Optional[int] = None,
) -> str:
    artifact_hash = _sha(_canon(metrics_json or {}))
    sql = """
    INSERT INTO tool_events (
      run_id, device_id, event_type, tool_name, tool_version,
      artifact_hash, input_data_ref, metrics_json, warnings_json, confidence,
      status, error_type, error_message, runtime_ms
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    """
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
                    status,
                    error_type,
                    error_message,
                    runtime_ms,
                ),
            )
        conn.commit()
    return artifact_hash


def latest_tool_events(
    device_id: str,
    tool_name: Optional[str] = None,
    limit: int = 10,
) -> List[Tuple[Any, ...]]:
    """
    Backward-compatible helper for older UI code.
    Returns rows ordered newest-first.

    Row structure (tuple) matches the earlier app expectation:
      (id, created_at, run_id, event_type, tool_name, tool_version, artifact_hash, metrics_json, warnings_json, confidence)
    """
    if tool_name:
        sql = """
        SELECT id, created_at, run_id, event_type, tool_name, tool_version, artifact_hash, metrics_json, warnings_json, confidence
        FROM tool_events
        WHERE device_id=%s AND tool_name=%s
        ORDER BY id DESC
        LIMIT %s;
        """
        params = (device_id, tool_name, int(limit))
    else:
        sql = """
        SELECT id, created_at, run_id, event_type, tool_name, tool_version, artifact_hash, metrics_json, warnings_json, confidence
        FROM tool_events
        WHERE device_id=%s
        ORDER BY id DESC
        LIMIT %s;
        """
        params = (device_id, int(limit))

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


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
                """
                INSERT INTO audit_chain (run_id, device_id, event_type, payload_json, prev_hash, event_hash)
                VALUES (%s,%s,%s,%s,%s,%s);
                """,
                (run_id, device_id, event_type, Json(payload_json), prev_hash, event_hash),
            )
        conn.commit()

    return event_hash

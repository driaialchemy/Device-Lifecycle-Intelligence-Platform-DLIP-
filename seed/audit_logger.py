from __future__ import annotations
from typing import Any, Dict
from db_persist import append_audit_chain

class AuditLogger:
    def __init__(self, run_id: str, device_id: str):
        self.run_id = run_id
        self.device_id = device_id

    def log_section(self, event_type: str, payload: Dict[str, Any]) -> str:
        return append_audit_chain(self.run_id, self.device_id, event_type, payload)

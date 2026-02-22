from __future__ import annotations

import hashlib
import datetime
from typing import Dict, Any

from agent_r2v3 import AgentR2V3
from agent_gdpr import AgentGDPR
from agent_sensor import AgentSensorHealth

from verifier import VerificationModule
from arbiter import BlindArbiter
from meta_reviewer import MetaReviewer
from seed_manager import set_global_seed

from db_persist import persist_run, persist_agent_output
from audit_logger import AuditLogger


class Orchestrator:
    """
    Multi-agent audit orchestrator:
    - Round 1: independent opinions
    - Round 2: adversarial challenge (anonymized)
    - Verification (CoVe-lite)
    - Blind arbiter decision
    - Meta-review: demo-grade long-form report + uncertainty
    - Hash-chained audit trail
    """

    def __init__(self):
        set_global_seed(42)
        self.agents = {
            "R2v3": AgentR2V3(),
            "GDPR": AgentGDPR(),
            "SensorHealth": AgentSensorHealth(),
        }
        self.verifier = VerificationModule()
        self.arbiter = BlindArbiter()
        self.meta = MetaReviewer()

    def run_device_audit(self, device_dict: Dict[str, Any]) -> Dict[str, Any]:
        run_id = self._generate_run_id(device_dict)
        device_id = device_dict.get("device_id", "unknown")

        persist_run(run_id, device_id)
        logger = AuditLogger(run_id, device_id)
        logger.log_section("RUN_START", {"run_id": run_id, "device_id": device_id})

        round1 = {}
        for name, agent in self.agents.items():
            op = agent.round1(device_dict)
            round1[name] = op
            persist_agent_output(run_id, device_id, op)
            logger.log_section(f"ROUND1_{name}", op)

        anonymized = [v for v in round1.values()]
        round2 = {}
        for name, agent in self.agents.items():
            op = agent.round2(anonymized)
            round2[name] = op
            logger.log_section(f"ROUND2_{name}", op)

        cove = self.verifier.verify(device_dict, round1, round2)
        logger.log_section("COVE_REPORT", cove)

        arb = self.arbiter.adjudicate(round1, round2, cove)
        logger.log_section("ARBITER", arb)

        meta = self.meta.review(
            provisional_decision=arb,
            device_dict=device_dict,
            cove_report=cove,
            round1_outputs=round1,
            round2_outputs=round2,
        )
        logger.log_section("META_REVIEW", meta)

        final_report = meta.get("final_report", "")
        final_uncertainty = meta.get("final_uncertainty", 0.85)
        logger.log_section("RUN_FINAL", {"final_uncertainty": final_uncertainty})

        audit_record = {
            "run_id": run_id,
            "device_id": device_id,
            "round1": round1,
            "round2": round2,
            "cove": cove,
            "arbiter": arb,
            "meta": meta,
            "final_report": final_report,
            "final_uncertainty": final_uncertainty,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }

        return {
            "final_report": final_report,
            "final_uncertainty": final_uncertainty,
            "run_id": run_id,
            "audit_record": audit_record,
        }

    def _generate_run_id(self, device_dict: Dict[str, Any]) -> str:
        base = f"{datetime.datetime.utcnow().isoformat()}_{device_dict.get('device_id','unknown')}"
        return "run_" + hashlib.sha256(base.encode()).hexdigest()[:12]

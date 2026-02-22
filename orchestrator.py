import hashlib, datetime
from agent_r2v3 import AgentR2V3
from agent_gdpr import AgentGDPR
from agent_sensor import AgentSensorHealth
from verifier import VerificationModule
from arbiter import BlindArbiter
from meta_reviewer import MetaReviewer
from audit_logger import AuditLogger
from llm_client import verify_llm_provider_available

class Orchestrator:
    def __init__(self):
        verify_llm_provider_available()
        self.logger = AuditLogger("audit_logs")
        self.agents = {"R2v3": AgentR2V3(), "GDPR": AgentGDPR(), "Sensor": AgentSensorHealth()}
        self.verifier = VerificationModule()
        self.arbiter = BlindArbiter()
        self.meta = MetaReviewer()

    def run_device_audit(self, device):
        rid = f"run_{hashlib.sha256((datetime.datetime.utcnow().isoformat()+str(device.get('device_id'))).encode()).hexdigest()[:8]}"
        self.logger.start_new_run(rid, device.get("device_id"))

        # Round 1
        r1 = {n: a.round1(device) for n, a in self.agents.items()}
        for n, o in r1.items(): self.logger.log_section(f"R1-{n}", o)

        # Round 2
        anon = list(r1.values())
        r2 = {n: a.round2(anon) for n, a in self.agents.items()}
        for n, o in r2.items(): self.logger.log_section(f"R2-{n}", o)

        # Verification & Arbitration
        cove = self.verifier.verify(device, r1, r2)
        self.logger.log_section("COVE", cove)
        arb = self.arbiter.adjudicate(r1, r2, cove)
        self.logger.log_section("ARBITER", arb)

        # Meta Review
        meta = self.meta.review(arb, device, cove)
        self.logger.log_section("META", meta)

        rec = {
            "run_id": rid, "timestamp": datetime.datetime.utcnow().isoformat(),
            "final_narrative": meta.get("adjusted_narrative", arb["fused_narrative"]),
            "final_uncertainty": meta.get("final_uncertainty", arb["fused_uncertainty"]),
            "details": {"r1": r1, "r2": r2, "cove": cove, "arb": arb, "meta": meta}
        }
        self.logger.log_section("FINAL", rec)
        self.logger.end_run()
        return rec
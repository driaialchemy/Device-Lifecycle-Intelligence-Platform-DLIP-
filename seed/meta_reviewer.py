from __future__ import annotations

from typing import Any, Dict, List, Optional
import os

from llm_client import LLMClient, verify_llm_provider_available


def _llm_optional(provider: str) -> Optional[LLMClient]:
    try:
        verify_llm_provider_available(provider)
        return LLMClient(provider=provider)
    except Exception:
        return None


def _shorten(text: str, max_chars: int = 800) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3].rstrip() + "..."


class MetaReviewer:
    """
    Produces a LONG-FORM, demo-grade report that showcases:
    - Multi-agent depth
    - Disagreement handling
    - Verification gates
    - Conservative uncertainty
    """

    def review(
        self,
        provisional_decision: Dict[str, Any],
        device_dict: Dict[str, Any],
        cove_report: Dict[str, Any],
        round1_outputs: Dict[str, Any],
        round2_outputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        # conservative uncertainty model
        unc = 0.35
        if (cove_report or {}).get("missing_device_fields"):
            unc += 0.15
        if (cove_report or {}).get("tool_errors"):
            unc += 0.20
        unc = min(0.95, unc)

        report = self._build_full_report(
            device_dict=device_dict,
            provisional_decision=provisional_decision,
            cove_report=cove_report,
            round1_outputs=round1_outputs,
            round2_outputs=round2_outputs,
            uncertainty=unc,
        )

        return {
            "final_report": report,
            "final_uncertainty": unc,
        }

    def _build_full_report(
        self,
        device_dict: Dict[str, Any],
        provisional_decision: Dict[str, Any],
        cove_report: Dict[str, Any],
        round1_outputs: Dict[str, Any],
        round2_outputs: Dict[str, Any],
        uncertainty: float,
    ) -> str:
        # attempt LLM-generated “boardroom” report (if keys present)
        client = _llm_optional("openai")

        if client:
            prompt = f"""
You are writing a demo-grade, executive audit report for a Device Passport system.
Goal: showcase multi-agent reasoning, evidence discipline, and arbitration.

DEVICE (JSON-ish dict):
{device_dict}

ROUND 1 OUTPUTS (agents, independent):
{round1_outputs}

ROUND 2 OUTPUTS (agents challenging each other):
{round2_outputs}

VERIFICATION REPORT (CoVe-lite):
{cove_report}

PROVISIONAL ARBITER DECISION:
{provisional_decision}

Write a detailed report with exactly these sections:

1) EXECUTIVE SUMMARY (5–8 sentences)
2) DEVICE PROFILE (key fields only)
3) AGENT FINDINGS (R2v3, GDPR, SensorHealth) — for each: claim, evidence used, risk rating, uncertainty, gaps
4) DISAGREEMENTS & RESOLUTION — what differed and how arbitration resolved it
5) VERIFICATION GATES (FACT CHECK / REFLECTION / COGNITIVE VERIFICATION)
6) FINAL DECISION & REFURB ACTIONS — include thresholds, re-test steps, and what would change the decision
7) LIMITATIONS — what this audit cannot conclude
8) NEXT DATA TO COLLECT — specific DB fields or sensor windows

Constraints:
- No raw JSON blocks in the report.
- Do not invent facts not present in the device or outputs.
- Be conservative when evidence is missing.
"""
            return client.complete(prompt, max_tokens=1200)

        # deterministic fallback (still much richer than today)
        device_id = device_dict.get("device_id")
        brand = device_dict.get("brand")
        model = device_dict.get("model")
        serial = device_dict.get("serial_number")

        arb_risk = provisional_decision.get("arbiter_risk_rating", "Medium")
        issues = provisional_decision.get("verifier_issues") or []
        missing = (cove_report or {}).get("missing_device_fields") or []
        tool_errs = (cove_report or {}).get("tool_errors") or []

        r2 = round1_outputs.get("R2v3") or {}
        g = round1_outputs.get("GDPR") or {}
        s = round1_outputs.get("SensorHealth") or {}

        def agent_block(name: str, out: Dict[str, Any]) -> str:
            return f"""- {name}
  - Risk rating: {out.get("risk_rating", "N/A")}
  - Uncertainty: {out.get("uncertainty", "N/A")}
  - Key stance: {out.get("stance", "N/A")}
  - Evidence summary: {_shorten(str((out.get("tool_outputs") or {})), 400)}
  - Narrative excerpt: {_shorten(out.get("text", ""), 500)}
"""

        return f"""1) EXECUTIVE SUMMARY
This Device Passport audit evaluated compliance (R2v3), privacy (GDPR), and sensor integrity posture (SensorHealth) using a multi-agent workflow with verification and arbitration.
The arbiter produced a conservative overall rating of: {arb_risk}.
Overall uncertainty is {uncertainty:.2f} (higher means less confidence), driven by verification issues and/or missing evidence.
This report is evidence-bounded: it does not infer facts beyond stored device metadata and agent outputs.

2) DEVICE PROFILE
- Device: {device_id} | {brand} {model}
- Serial: {serial}

3) AGENT FINDINGS
{agent_block("R2v3", r2)}
{agent_block("GDPR", g)}
{agent_block("SensorHealth", s)}

4) DISAGREEMENTS & RESOLUTION
- Arbiter evidence inputs: {provisional_decision.get("supporting_evidence", [])}
- Resolution rule: conservative selection of highest plausible risk given evidence gaps.

5) VERIFICATION GATES (FACT CHECK / REFLECTION / COGNITIVE VERIFICATION)
- Missing device fields: {missing}
- Tool errors present: {tool_errs}
- Verifier issues flagged: {issues}

6) FINAL DECISION & REFURB ACTIONS
- Final risk rating: {arb_risk}
- Recommended actions:
  1) Confirm wipe/erasure evidence when GDPR flags exist.
  2) Run FFT on multiple windows and cross-sensor compare (accel vs gyro) for stability.
  3) If battery health is trending down steeply, route to repair or swap battery.

7) LIMITATIONS
- This report does not validate ground-truth outcomes; it is an evidence-based screening.
- Absent explicit tool events (FFT/forecast), sensor conclusions remain conservative.

8) NEXT DATA TO COLLECT
- Add repeated sensor windows per device (multiple sessions) in sensor_timeseries.
- Add usage/cycle counts if available to strengthen forecasts.
"""

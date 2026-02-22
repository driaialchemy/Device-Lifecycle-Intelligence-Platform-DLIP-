# meta_reviewer.py
# MetaReviewer = Final oversight layer: reflection + cognitive verification.
# Deterministic, rule-based, no LLM output.

from typing import Dict, Any


class MetaReviewer:
    """
    MetaReviewer
    -----------------------------
    Responsibilities:
      1. Reflection:
         - Identify where reasoning may have failed.
         - Detect missing perspectives (e.g., sensor risk ignored in compliance discussion).
         - Highlight data gaps or overconfidence.

      2. Cognitive Verification:
         - Check for contradictions between sections.
         - Check whether uncertainty levels align with evidence strength.
         - Check whether final fused narrative appropriately integrates cross-domain risks.

    Produces:
      - adjusted_narrative
      - final_uncertainty
      - notes (dict summarizing findings)
    """

    def review(
        self,
        provisional_decision: Dict[str, Any],
        device_dict: Dict[str, Any],
        cove_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Main entrypoint, returns dictionary with:
            - adjusted_narrative
            - final_uncertainty
            - notes (reflection + cognitive verification)
        """
        fused_narrative = provisional_decision.get("fused_narrative", "")
        fused_uncertainty = provisional_decision.get("fused_uncertainty", 0.5)
        ranking = provisional_decision.get("ranking", [])

        notes = {
            "reflection_findings": [],
            "cognitive_verification_flags": [],
        }

        # ---------------------------------------------------------
        # 1. REFLECTION ROUND
        # ---------------------------------------------------------

        # If narrative seems overly confident given uncertainty
        if fused_uncertainty > 0.8:
            notes["reflection_findings"].append(
                "High uncertainty detected; narrative may overstate confidence."
            )

        # If GDPR or Sensor domain risks differ strongly from R2v3:
        domain_mismatch = self._detect_cross_domain_mismatch(ranking)
        if domain_mismatch:
            notes["reflection_findings"].append(domain_mismatch)

        # If CoVe indicates major contradictions
        overall_flags = cove_report.get("overall", {}).get("cross_agent_consistency", [])
        if any("UNCERTAIN" in f for f in overall_flags):
            notes["reflection_findings"].append(
                "CoVe flagged significant inconsistencies across agent assessments."
            )

        # ---------------------------------------------------------
        # 2. COGNITIVE VERIFICATION ROUND
        # ---------------------------------------------------------

        # Check for contradictions within the fused narrative
        contradictions = self._detect_internal_contradictions(fused_narrative)
        if contradictions:
            notes["cognitive_verification_flags"].append(contradictions)

        # Verify uncertainty matches evidence strength
        adjusted_uncertainty = self._adjust_uncertainty(
            fused_uncertainty,
            cove_report,
            ranking
        )

        # If uncertainty is increased meaningfully, annotate narrative
        if adjusted_uncertainty > fused_uncertainty + 0.05:
            notes["cognitive_verification_flags"].append(
                "Uncertainty increased due to verification inconsistencies."
            )
            fused_narrative += (
                "\n\nFINAL UNCERTAINTY NOTE:\n"
                "The uncertainty for this assessment was increased due to identified "
                "cross-agent inconsistencies and evidence gaps."
            )

        return {
            "adjusted_narrative": fused_narrative,
            "final_uncertainty": adjusted_uncertainty,
            "notes": notes
        }

    # ------------------------------------------------------------------
    # INTERNAL UTILITIES
    # ------------------------------------------------------------------

    def _detect_cross_domain_mismatch(self, ranking: list) -> str:
        """
        Checks if risk ratings diverge heavily across domains.
        """
        ratings = [r.get("risk_rating", "").lower() for r in ranking]

        if "critical" in ratings and "low" in ratings:
            return "Large cross-domain risk mismatch detected (Critical vs Low)."

        if "high" in ratings and "low" in ratings:
            return "Agent disagreement detected: High vs Low risk ratings."

        return ""

    def _detect_internal_contradictions(self, text: str) -> str:
        """
        Basic plain-text contradiction detection.
        """
        t = text.lower()

        contradictions = []

        if "high risk" in t and "minimal risk" in t:
            contradictions.append("Narrative contains conflicting descriptions of risk.")

        if "complete certainty" in t and "high uncertainty" in t:
            contradictions.append("Narrative inconsistently describes certainty.")

        if contradictions:
            return "; ".join(contradictions)
        return ""

    def _adjust_uncertainty(
        self,
        fused_uncertainty: float,
        cove_report: Dict[str, Any],
        ranking: list
    ) -> float:
        """
        Adjusts uncertainty based on CoVe results and ranking differences.
        """
        adjusted = fused_uncertainty

        # If CoVe found major inconsistencies increase uncertainty
        overall = cove_report.get("overall", {})
        flags = overall.get("cross_agent_consistency", [])

        if any("UNCERTAIN" in f for f in flags):
            adjusted += 0.1

        # If bottom-ranked opinions scored extremely low, suggests disagreement
        if ranking:
            scores = [r["score_breakdown"]["total_score"] for r in ranking]
            if max(scores) - min(scores) > 12:
                adjusted += 0.05

        # Clamp to [0,1]
        adjusted = max(0.0, min(1.0, adjusted))
        return adjusted

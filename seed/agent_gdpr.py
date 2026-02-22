import random
from typing import Any, Dict, List
from llm_client import LLMClient, verify_llm_provider_available

class AgentGDPR:
    def __init__(self):
        self.name = "Agent_GDPR"
        self.domain = "GDPR"
        self.stance = random.choice(["privacy-first","sceptical of erasure claims","evidence-maximizing"])
        self.llm = None
        try:
            verify_llm_provider_available("gemini")
            self.llm = LLMClient(provider="gemini")
        except Exception:
            self.llm = None

    def round1(self, device_dict: Dict[str, Any]) -> Dict[str, Any]:
        flags = device_dict.get("gdpr_flags") or {}
        score = sum(1 for v in flags.values() if v)
        risk = "Low" if score == 0 else ("Medium" if score <= 1 else "High")

        text = (
            "NARRATIVE:\n"
            f"GDPR flags count={score}.\n"
            "SUMMARY:\nConservative privacy posture.\n"
            "RISK RATING:\n"
            f"{risk}\n"
            "UNCERTAINTY:\n0.50\n"
            "KEY EVIDENCE:\n"
            f"{flags}"
        )

        if self.llm:
            prompt = f"""You are a GDPR and data protection specialist.
DEVICE CONTEXT:
{device_dict}
Assess residual data and erasure risk conservatively.
Write: NARRATIVE, SUMMARY, RISK RATING, UNCERTAINTY, KEY EVIDENCE.
Do not invent facts."""
            text = self.llm.complete(prompt, max_tokens=650)

        return {
            "agent": self.name,
            "domain": self.domain,
            "stance": self.stance,
            "round": 1,
            "text": text,
            "risk_rating": risk,
            "uncertainty": 0.50,
            "tool_outputs": {"gdpr_flags": flags, "flag_count": score},
        }

    def round2(self, anonymized_opinions: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = (
            "NARRATIVE:\nReviewed anonymized opinions; emphasize privacy risk when evidence is incomplete.\n"
            "SUMMARY:\nRisk remains non-zero absent strong erasure proofs.\n"
            "UPDATED UNCERTAINTY:\n0.55"
        )
        if self.llm:
            prompt = f"""Review anonymized GDPR opinions.
OPINIONS:
{anonymized_opinions}
Challenge understated privacy risk and update uncertainty."""
            text = self.llm.complete(prompt, max_tokens=500)

        return {
            "agent": self.name,
            "domain": self.domain,
            "stance": self.stance,
            "round": 2,
            "text": text,
            "updated_uncertainty": 0.55,
        }

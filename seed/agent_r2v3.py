import random
from typing import Any, Dict, List
from llm_client import LLMClient, verify_llm_provider_available

class AgentR2V3:
    def __init__(self):
        self.name = "Agent_R2v3"
        self.domain = "R2v3"
        self.stance = random.choice(["risk-minimizing","compliance-first","evidence-maximizing"])
        self.llm = None
        try:
            verify_llm_provider_available("openai")
            self.llm = LLMClient(provider="openai")
        except Exception:
            self.llm = None

    def round1(self, device_dict: Dict[str, Any]) -> Dict[str, Any]:
        flags = device_dict.get("r2v3_flags") or {}
        score = sum(1 for v in flags.values() if v)
        risk = "Low" if score == 0 else ("Medium" if score <= 1 else "High")

        text = (
            "NARRATIVE:\n"
            f"R2v3 flags count={score}.\n"
            "SUMMARY:\nConservative compliance posture.\n"
            "RISK RATING:\n"
            f"{risk}\n"
            "UNCERTAINTY:\n0.45\n"
            "KEY EVIDENCE:\n"
            f"{flags}"
        )

        if self.llm:
            prompt = f"""You are an R2v3 compliance specialist.
DEVICE CONTEXT:
{device_dict}
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
            "uncertainty": 0.45,
            "tool_outputs": {"r2v3_flags": flags, "flag_count": score},
        }

    def round2(self, anonymized_opinions: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = (
            "NARRATIVE:\nReviewed anonymized opinions; no new evidence provided beyond flags.\n"
            "SUMMARY:\nMaintain conservative posture.\n"
            "UPDATED UNCERTAINTY:\n0.50"
        )
        if self.llm:
            prompt = f"""Review anonymized R2v3 opinions.
OPINIONS:
{anonymized_opinions}
Challenge weak reasoning and update uncertainty."""
            text = self.llm.complete(prompt, max_tokens=500)

        return {
            "agent": self.name,
            "domain": self.domain,
            "stance": self.stance,
            "round": 2,
            "text": text,
            "updated_uncertainty": 0.50,
        }

import random
from typing import Any, Dict, List
from llm_client import LLMClient, verify_llm_provider_available

class AgentSensorHealth:
    def __init__(self):
        self.name = "Agent_SensorHealth"
        self.domain = "SensorHealth"
        self.stance = random.choice(["data-quality-first","degradation-sensitive","sensor-reliability-focused"])
        self.llm = None
        try:
            verify_llm_provider_available("openai")
            self.llm = LLMClient(provider="openai")
        except Exception:
            self.llm = None

    def round1(self, device_dict: Dict[str, Any]) -> Dict[str, Any]:
        text = (
            "NARRATIVE:\nSensor health should be supported by quantitative checks (PSD/FFT, noise floor, drift) using DB time-series.\n"
            "SUMMARY:\nRun FFT + forecasting tools and log to tool_events.\n"
            "RISK RATING:\nMedium\n"
            "UNCERTAINTY:\n0.55\n"
            "KEY EVIDENCE:\nTime-series analysis executed separately."
        )
        if self.llm:
            prompt = f"""You are a sensor health and degradation specialist.
DEVICE CONTEXT:
{device_dict}
Provide a conservative sensor health risk assessment.
Do not invent facts."""
            text = self.llm.complete(prompt, max_tokens=650)

        return {
            "agent": self.name,
            "domain": self.domain,
            "stance": self.stance,
            "round": 1,
            "text": text,
            "risk_rating": "Medium",
            "uncertainty": 0.55,
            "tool_outputs": {"note": "Use sensor_timeseries + battery_history for quantitative checks."},
        }

    def round2(self, anonymized_opinions: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = (
            "NARRATIVE:\nChallenge: require PSD and drift metrics to support claims.\n"
            "SUMMARY:\nRecommend repeated windows and cross-sensor validation.\n"
            "UPDATED UNCERTAINTY:\n0.60"
        )
        if self.llm:
            prompt = f"""Review anonymized opinions.
OPINIONS:
{anonymized_opinions}
Challenge claims that ignore sensor reliability and update uncertainty."""
            text = self.llm.complete(prompt, max_tokens=500)

        return {
            "agent": self.name,
            "domain": self.domain,
            "stance": self.stance,
            "round": 2,
            "text": text,
            "updated_uncertainty": 0.60,
        }

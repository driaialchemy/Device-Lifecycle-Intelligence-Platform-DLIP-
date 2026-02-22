import random
from llm_client import LLMClient
from tools import evaluate_sensor_health
class AgentSensorHealth:
    def __init__(self): self.name="Sensor"; self.llm=LLMClient("openai")
    def round1(self, dev):
        tools = {"sens": evaluate_sensor_health(dev)}
        txt = self.llm.complete(f"Sensor Audit {dev} {tools} fmt: NARRATIVE, RISK RATING, UNCERTAINTY")
        return {"agent":self.name, "round":1, "text":txt, "risk_rating":"Low", "uncertainty":0.2, "tool_outputs":tools}
    def round2(self, ops):
        txt = self.llm.complete(f"Critique {ops}")
        return {"agent":self.name, "round":2, "text":txt, "updated_uncertainty":0.1}
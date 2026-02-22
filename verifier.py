class VerificationModule:
    def verify(self, dev, r1, r2):
        rep = {"agents": {}, "overall": {}}
        for ag, op in r1.items():
            rep["agents"][ag] = self._v_r1(op)
            rep["agents"][ag]["r2_review"] = self._v_r2(r2.get(ag))
        return rep

    def _v_r1(self, op):
        flags = []
        txt = str(op.get("text", "")).upper()
        if "NARRATIVE:" not in txt: flags.append("UNCERTAIN: Missing Narrative")
        tools = op.get("tool_outputs", {})
        for t, out in tools.items():
            if "high" in str(out).lower() and "low risk" in txt.lower():
                flags.append(f"CONTRADICTED: Tool {t} says high risk, text says low.")
        return {"round1_verification": flags or ["VERIFIED"]}

    def _v_r2(self, op):
        if not op: return ["UNCERTAIN: Missing R2"]
        txt = str(op.get("text", "")).lower()
        if "fabricated" in txt: return ["CONTRADICTED: Improper fabrication accusation"]
        return ["VERIFIED"]
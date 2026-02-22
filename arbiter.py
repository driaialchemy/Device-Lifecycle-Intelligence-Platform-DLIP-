class BlindArbiter:
    def adjudicate(self, r1, r2, cove):
        ops = []
        for ag, o1 in r1.items():
            ops.append({
                "text": o1.get("text",""), "risk": o1.get("risk_rating","Medium"),
                "unc": o1.get("uncertainty",0.5), "up_unc": r2.get(ag,{}).get("updated_uncertainty"),
                "ver": cove["agents"].get(ag,{})
            })
        
        scored = []
        for i, op in enumerate(ops):
            score = 5
            if any("CONTRADICTED" in str(f) for f in op["ver"].values()): score = 1
            if op["up_unc"] is not None: score += 2
            scored.append((score, op))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        
        # Fuse
        w_unc = sum((o["up_unc"] or o["unc"])*s for s,o in scored) / sum(s for s,_ in scored)
        return {
            "fused_narrative": best["text"],
            "fused_uncertainty": w_unc,
            "risk_rating": best["risk"],
            "ranking": [s for s,_ in scored]
        }
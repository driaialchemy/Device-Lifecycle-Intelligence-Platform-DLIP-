from typing import Any, Dict

class BlindArbiter:
    ORDER={'low':1,'medium':2,'high':3,'critical':4}
    def adjudicate(self, round1_outputs: Dict[str, Any], round2_outputs: Dict[str, Any], cove_report: Dict[str, Any]) -> Dict[str, Any]:
        worst=('Medium',2)
        evidence=[]
        for name,out in (round1_outputs or {}).items():
            rr=str((out or {}).get('risk_rating','Medium'))
            score=self.ORDER.get(rr.strip().lower(),2)
            if score>=worst[1]:
                worst=(rr,score)
            evidence.append({'agent':name,'risk_rating':rr})
        issues=[]
        if (cove_report or {}).get('missing_device_fields'):
            issues.append('missing_device_fields')
        if (cove_report or {}).get('tool_errors'):
            issues.append('tool_errors_present')
        return {'arbiter_risk_rating':worst[0],'supporting_evidence':evidence,'verifier_issues':issues}

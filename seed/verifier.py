from typing import Any, Dict

class VerificationModule:
    def verify(self, device_dict: Dict[str, Any], round1: Dict[str, Any], round2: Dict[str, Any]) -> Dict[str, Any]:
        missing=[k for k in ['device_id','brand','model'] if not device_dict.get(k)]
        tool_errors=[]
        for agent,out in (round1 or {}).items():
            tools=(out or {}).get('tool_outputs') or {}
            if 'tool_error' in tools:
                tool_errors.append({'agent':agent,'error':tools.get('tool_error')})
        return {'missing_device_fields':missing,'tool_errors':tool_errors}

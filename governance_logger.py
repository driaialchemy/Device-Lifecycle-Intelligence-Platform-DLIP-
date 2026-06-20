"""Python governance logger - mirrors @driaialchemy/governance-logger API."""

import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore


def _governor_url() -> str:
    return os.environ.get("GOVERNANCE_URL", "http://localhost:3000")


def log_success(agent_id: str, description: str, output: Optional[Any] = None) -> bool:
    """Log a successful agent execution to the governance governor."""
    if requests is None:
        return False

    activity = {
        "agentId": agent_id,
        "actionType": "agent_execution_complete",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "result": {"success": True, "output": output},
    }

    try:
        response = requests.post(
            f"{_governor_url()}/agents/{agent_id}/activity",
            json=activity,
            timeout=int(os.environ.get("GOVERNANCE_TIMEOUT", "5000")) / 1000,
        )
        return response.status_code == 200
    except Exception as exc:
        print(f"[GovernanceLogger] Failed to log activity for {agent_id}: {exc}")
        return False


def log_error(agent_id: str, error: str) -> bool:
    """Log an agent error to the governance governor."""
    if requests is None:
        return False

    activity = {
        "agentId": agent_id,
        "actionType": "error_occurred",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": f"Error: {error}",
        "result": {"success": False, "error": error},
    }

    try:
        response = requests.post(
            f"{_governor_url()}/agents/{agent_id}/activity",
            json=activity,
            timeout=int(os.environ.get("GOVERNANCE_TIMEOUT", "5000")) / 1000,
        )
        return response.status_code == 200
    except Exception as exc:
        print(f"[GovernanceLogger] Failed to log error for {agent_id}: {exc}")
        return False

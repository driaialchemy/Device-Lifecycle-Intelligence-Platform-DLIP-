import json
import os

import pandas as pd
import streamlit as st

from db_access import (
    compute_arbiter_risk_distribution,
    count_devices,
    fetch_audit_chain,
    fetch_recent_runs,
    fetch_runs_for_device,
    get_device_payload,
    init_db_schema,
    list_devices,
)
from db_persist import persist_run
from orchestrator import Orchestrator

# ------------------------------------------------------------------------------
# 1. SETUP & SIDEBAR (Must be at the very top)
# ------------------------------------------------------------------------------
st.set_page_config(page_title="Device Passport", page_icon="🛡️", layout="wide")

st.sidebar.title("Device Passport")
st.sidebar.markdown("---")
role = st.sidebar.selectbox("Select Role", ["Operator", "Engineering", "Executive"])
st.sidebar.caption(f"Logged in as: **{role}**")


# ------------------------------------------------------------------------------
# 2. HELPER FUNCTIONS (Formatting Logic)
# ------------------------------------------------------------------------------
def format_flags(title: str, data):
    """Parse dict-like flag payloads and render readable bullets."""
    st.markdown(f"#### {title}")

    # Handle stringified JSON if database returns strings.
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            st.error(f"Could not parse data for {title}")
            return

    if not data or not isinstance(data, dict):
        st.info("No flags set.")
        return

    for key, val in data.items():
        label = key.replace("_", " ").title()
        if val is True:
            icon, text = "✅", "Yes"
        elif val is False:
            icon, text = "❌", "No"
        else:
            icon, text = "🔹", str(val)
        st.markdown(f"{icon} **{label}**: {text}")


def device_registry_dataframe(devices: list[dict]) -> pd.DataFrame:
    rows = []
    for device in devices:
        payload = device.get("device_payload") or {}
        rows.append(
            {
                "device_id": device.get("device_id"),
                "brand": payload.get("brand"),
                "model": payload.get("model"),
                "region": payload.get("region"),
                "firmware_version": payload.get("firmware_version"),
                "purchase_date": payload.get("purchase_date"),
                "serial_number": payload.get("serial_number"),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------
# 3. DATABASE CONNECTION
# ------------------------------------------------------------------------------
try:
    init_db_schema()
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()


# ------------------------------------------------------------------------------
# 4. VIEW LOGIC
# ------------------------------------------------------------------------------

# === OPERATOR VIEW ===
if role == "Operator":
    st.title("🎛️ Operator Dashboard")

    devices = list_devices(limit=50)
    if not devices:
        st.warning("Database empty. Run the seed script.")
        st.stop()

    dev_map = {
        f"{d['device_id']} | {d.get('device_payload', {}).get('brand', 'Unknown')}": d["device_id"]
        for d in devices
    }
    selected_label = st.selectbox("Select Device to Inspect", list(dev_map.keys()))
    device_id = dev_map[selected_label]

    payload = get_device_payload(device_id)

    tab1, tab2, tab3 = st.tabs(["📋 Overview (Readable)", "🤖 Run Audit", "🔒 Audit Chain"])

    with tab1:
        st.subheader(f"Device: {device_id}")

        c1, c2 = st.columns(2)

        with c1:
            format_flags("GDPR & Privacy Status", payload.get("gdpr_flags", {}))

        with c2:
            format_flags("R2v3 Compliance", payload.get("r2v3_flags", {}))

        st.divider()
        with st.expander("🛠️ View Raw JSON Data (Debug Only)"):
            st.json(payload)

    with tab2:
        st.subheader("Multi-Agent Compliance Audit")

        missing_llm_keys = [
            key for key in ("OPENAI_API_KEY", "GEMINI_API_KEY") if not os.getenv(key)
        ]
        if missing_llm_keys:
            st.warning(
                "Set these environment variables in .env before running an audit: "
                + ", ".join(missing_llm_keys)
            )

        if st.button("🚀 Start Audit", type="primary", disabled=bool(missing_llm_keys)):
            with st.spinner("Agents are negotiating..."):
                try:
                    orch = Orchestrator()
                    result = orch.run_device_audit(payload)
                    persist_run(result["run_id"], device_id)
                except Exception as exc:
                    st.error(f"Audit failed: {exc}")
                    st.stop()

            st.success(f"Audit Complete! Run ID: {result['run_id']}")

            st.markdown("### 📝 Final Consensus Narrative")
            st.info(result.get("final_narrative", "No narrative generated."))

            st.metric("Uncertainty Score", f"{result.get('final_uncertainty', 0):.2f}")

            st.markdown("### 🕵️ Agent Opinions")
            r1 = (
                result.get("audit_record", {}).get("round1", {})
                or result.get("details", {}).get("round1", {})
                or result.get("details", {}).get("r1", {})
            )

            if not isinstance(r1, dict) or not r1:
                st.info("No agent opinions were returned for this run.")

            for agent_name, agent_data in (r1.items() if isinstance(r1, dict) else []):
                if not isinstance(agent_data, dict):
                    continue
                with st.expander(f"Agent: {agent_name} (Click to expand)"):
                    st.markdown(agent_data.get("text", "No text provided."))
                    st.caption("Raw Tool Outputs:")
                    st.json(agent_data.get("tool_outputs", {}))

    with tab3:
        st.subheader("Immutable Ledger")
        runs = fetch_runs_for_device(device_id)

        if not runs.empty:
            run_id = st.selectbox("Select Past Run", runs["run_id"].unique())
            chain = fetch_audit_chain(run_id)

            if not chain.empty:
                for _, row in chain.iterrows():
                    etype = row.get("event_type")
                    ts = row.get("created_at")
                    raw_payload = row.get("payload_json")

                    if isinstance(raw_payload, str):
                        try:
                            payload_json = json.loads(raw_payload)
                        except Exception:
                            payload_json = raw_payload
                    else:
                        payload_json = raw_payload

                    with st.expander(f"{ts} | {etype}"):
                        st.write(payload_json)
            else:
                st.info("No events found for this run.")
        else:
            st.info("No audit history for this device.")

# === ENGINEERING VIEW ===
elif role == "Engineering":
    st.title("🛠️ Engineering Console")
    st.info("This view focuses on system health and data integrity.")

    count = count_devices()
    st.metric("Total Devices in Registry", count)

    st.subheader("Device Registry")
    devices = list_devices(limit=100)
    if devices:
        st.dataframe(device_registry_dataframe(devices), use_container_width=True)
    else:
        st.warning("No devices found in device_registry. Run the seed script.")

    st.subheader("Recent Audit Runs")
    runs = fetch_recent_runs(limit=10)
    if not runs.empty:
        st.dataframe(runs, use_container_width=True)
    else:
        st.info("No audit runs yet. Start an audit from the Operator view to populate this table.")

# === EXECUTIVE VIEW ===
elif role == "Executive":
    st.title("📊 Executive Dashboard")

    runs = fetch_recent_runs(limit=100)
    total_audits = len(runs)

    risk_dist = compute_arbiter_risk_distribution(days=30)

    c1, c2 = st.columns(2)
    c1.metric("Audits (Last 30 Days)", total_audits)

    st.subheader("Risk Profile")
    if not risk_dist.empty:
        st.bar_chart(risk_dist.set_index("arbiter_risk_rating"))
    else:
        st.info("No sufficient data for risk charting.")

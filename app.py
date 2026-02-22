import streamlit as st
import json
import hashlib
import pandas as pd
from orchestrator import Orchestrator
from db_access import (
    init_db_schema, list_devices, get_device_payload, 
    fetch_runs_for_device, fetch_audit_chain, count_devices,
    fetch_recent_runs, compute_arbiter_risk_distribution
)
from db_persist import persist_run

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
def format_flags(title, data):
    """Parses JSON dict and prints clean bullets (No raw JSON)."""
    st.markdown(f"#### {title}")
    
    # Handle stringified JSON if database returns strings
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            st.error(f"Could not parse data for {title}")
            return

    if not data or not isinstance(data, dict):
        st.info("No flags set.")
        return

    # Render Bullets
    for key, val in data.items():
        # clean key name: 'gdpr_erasure_claimed' -> 'Gdpr Erasure Claimed'
        label = key.replace("_", " ").title()
        
        if val is True:
            icon = "✅"
            text = "Yes"
        elif val is False:
            icon = "❌"
            text = "No"
        else:
            icon = "🔹"
            text = str(val)
            
        st.markdown(f"{icon} **{label}**: {text}")

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
    
    # Fetch Devices
    devices = list_devices(limit=50)
    if not devices:
        st.warning("Database empty. Run the seed script.")
        st.stop()
        
    # Dropdown Selection
    dev_map = {f"{d['device_id']} | {d.get('device_payload',{}).get('brand','Unknown')}": d['device_id'] for d in devices}
    selected_label = st.selectbox("Select Device to Inspect", list(dev_map.keys()))
    device_id = dev_map[selected_label]
    
    # Get Data
    payload = get_device_payload(device_id)
    
    # Layout Tabs
    tab1, tab2, tab3 = st.tabs(["📋 Overview (Readable)", "🤖 Run Audit", "🔒 Audit Chain"])
    
    with tab1:
        st.subheader(f"Device: {device_id}")
        
        # COLUMNS FOR FLAGS (Human Readable)
        c1, c2 = st.columns(2)
        
        with c1:
            # Force extract dict keys for GDPR
            format_flags("GDPR & Privacy Status", payload.get("gdpr_flags", {}))
            
        with c2:
            # Force extract dict keys for R2v3
            format_flags("R2v3 Compliance", payload.get("r2v3_flags", {}))
            
        st.divider()
        with st.expander("🛠️ View Raw JSON Data (Debug Only)"):
            st.json(payload)

    with tab2:
        st.subheader("Multi-Agent Compliance Audit")
        
        if st.button("🚀 Start Audit", type="primary"):
            with st.spinner("Agents are negotiating..."):
                orch = Orchestrator()
                # Run the backend logic
                result = orch.run_device_audit(payload)
                # Save to DB
                persist_run(result["run_id"], device_id)
            
            st.success(f"Audit Complete! Run ID: {result['run_id']}")
            
            # SHOW NARRATIVE AS MARKDOWN (Not Dataframe)
            st.markdown("### 📝 Final Consensus Narrative")
            st.info(result.get("final_narrative", "No narrative generated."))
            
            st.metric("Uncertainty Score", f"{result.get('final_uncertainty', 0):.2f}")
            
            # SHOW AGENT DETAILS IN EXPANDERS (Prevents cutoff text)
            st.markdown("### 🕵️ Agent Opinions")
            
            # Round 1 outputs
            r1 = result.get("audit_record", {}).get("round1", {}) or result.get("details", {}).get("round1", {})
            
            for agent_name, agent_data in r1.items():
                with st.expander(f"Agent: {agent_name} (Click to expand)"):
                    # Use markdown so text wraps instead of cutting off
                    text = agent_data.get("text", "No text provided.")
                    st.markdown(text)
                    st.caption("Raw Tool Outputs:")
                    st.json(agent_data.get("tool_outputs", {}))

    with tab3:
        st.subheader("Immutable Ledger")
        runs = fetch_runs_for_device(device_id)
        
        if not runs.empty:
            run_id = st.selectbox("Select Past Run", runs["run_id"].unique())
            chain = fetch_audit_chain(run_id)
            
            # Show events as blocks, not just a table
            for i, row in chain.iterrows():
                etype = row['event_type']
                ts = row['created_at']
                
                # Format the payload for display
                try:
                    p_json = json.loads(row['payload_json'])
                except:
                    p_json = row['payload_json']
                
                with st.expander(f"{ts} | {etype}"):
                    st.write(p_json)
        else:
            st.info("No audit history for this device.")

# === ENGINEERING VIEW ===
elif role == "Engineering":
    st.title("🛠️ Engineering Console")
    st.info("This view focuses on system health and data integrity.")
    
    count = count_devices()
    st.metric("Total Devices in Registry", count)
    
    st.subheader("Raw Database View")
    runs = fetch_recent_runs(limit=10)
    st.dataframe(runs)

# === EXECUTIVE VIEW ===
elif role == "Executive":
    st.title("📊 Executive Dashboard")
    
    # Calculate simple stats
    runs = fetch_recent_runs(limit=100)
    total_audits = len(runs)
    
    # Dummy calculation for risk (replace with real if available)
    risk_dist = compute_arbiter_risk_distribution(days=30)
    
    c1, c2 = st.columns(2)
    c1.metric("Audits (Last 30 Days)", total_audits)
    
    st.subheader("Risk Profile")
    if not risk_dist.empty:
        st.bar_chart(risk_dist.set_index("arbiter_risk_rating"))
    else:
        st.info("No sufficient data for risk charting.")

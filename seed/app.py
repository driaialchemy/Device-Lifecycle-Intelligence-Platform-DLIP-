import streamlit as st
import pandas as pd
import json
import numpy as np
import os
from db_access import *
from db_persist import persist_run, persist_audit_log
from dsp_utils import run_fft_welch
from forecasting import forecast_with_uncertainty
from llm_client import LLMClient

st.set_page_config(page_title="Device Passport", layout="wide")

# --- UTILS ---
def render_clean(data):
    if isinstance(data, str):
        try: data = json.loads(data)
        except: st.write(data); return
    if isinstance(data, dict):
        if "text" in data: st.info(data["text"])
        else:
            items = []
            for k,v in data.items():
                if not isinstance(v, (list,dict)):
                    items.append({"Parameter": k.replace('_',' ').title(), "Status": v})
            if items:
                st.table(pd.DataFrame(items))
    elif isinstance(data, list):
        for i in data: st.write(f"- {i}")
    else: st.write(data)

def find_signal_events(data):
    arr = np.array(data)
    diffs = np.diff(arr)
    drop_idx = np.argmin(diffs) if len(diffs) > 0 else 0
    return {
        "current": arr[-1],
        "steepest_drop_idx": drop_idx,
        "steepest_drop_val": np.min(diffs) if len(diffs) > 0 else 0,
        "variance": np.var(arr)
    }

def show_device_dashboard(role_name):
    st.title(f"🎛️ {role_name} Console v8.0 (Final)")
    
    # --- DB PROTECTION ---
    try: devices = list_devices()
    except Exception: st.error("Database connection failed."); st.stop()
    if not devices: st.warning("Database empty."); st.stop()

    dev_map = {d['device_id']: d for d in devices}
    sel_id = st.selectbox("Select Asset ID", list(dev_map.keys()))
    payload = get_device_payload(sel_id)
    brand = payload.get("brand", "OEM")
    model = payload.get("model", "Hardware")
    
    # --- TABS ---
    tabs = st.tabs(["📋 Specs", "⚖️ Tribunal", "📈 Spectral", "🧠 Lifecycle", "🔒 Audit"])

    with tabs[0]: 
        c1, c2 = st.columns(2)
        with c1: st.subheader("Sanitization Specs"); render_clean(payload.get("gdpr_flags"))
        with c2: st.subheader("Functional Grading"); render_clean(payload.get("r2v3_flags"))

    # --- TAB 1: AGENTIC TRIBUNAL ---
    with tabs[1]: 
        st.subheader("Multi-Agent Adversarial Audit")
        st.info(f"Subject: {brand} {model}")
        
        if st.button("🚀 Launch Tribunal"):
            llm = LLMClient("gemini")
            rid = f"RUN-{pd.Timestamp.now().strftime('%H%M%S')}"
            persist_run(rid, sel_id)

            # AGENT A: PROSECUTOR
            with st.chat_message("user", avatar="🛑"):
                st.write("**Agent A (Risk Auditor):**")
                p1 = f"Act as Risk Auditor. Review {brand} {model}. Data: {payload}. Find strictly negative faults. Be aggressive."
                r1 = llm.complete(p1)
                st.write(r1)
                persist_audit_log(rid, "PROSECUTOR", {"text": r1})

            # AGENT B: DEFENDER
            with st.chat_message("assistant", avatar="🛡️"):
                st.write("**Agent B (Value Recovery):**")
                p2 = f"Act as Value Recovery. Defend {brand} {model}. Counter-argue: {r1}. Find value in parts."
                r2 = llm.complete(p2)
                st.write(r2)
                persist_audit_log(rid, "DEFENDER", {"text": r2})

            # ARBITER
            with st.chat_message("assistant", avatar="⚖️"):
                st.write("**The Arbiter:**")
                p3 = f"Act as Arbiter. {brand} {model}. Pros: {r1}. Def: {r2}. Issue Verdict: Resell vs Recycle."
                r3 = llm.complete(p3)
                st.markdown(f"### VERDICT:\n{r3}")
                persist_audit_log(rid, "VERDICT", {"text": r3})
            
            st.session_state['last_run'] = rid

        if 'last_run' in st.session_state:
            st.divider()
            chain = fetch_audit_chain(st.session_state['last_run'])
            for _, row in chain.iterrows():
                icon = "⚖️" if "VERDICT" in row['event_type'] else "🛑" if "PROSECUTOR" in row['event_type'] else "🛡️"
                with st.chat_message("assistant", avatar=icon):
                    st.write(f"**{row['event_type']}**")
                    render_clean(row['payload_json'])

    # --- TAB 2: SPECTRAL ---
    with tabs[2]: 
        st.subheader(f"{role_name} Signal Analysis")
        samples = payload.get("fft_samples")
        if samples:
            res = run_fft_welch(samples, 100)
            st.metric("SNR", f"{res['snr_db']:.1f} dB")
            st.line_chart(samples[:60])
            
            if st.button("Generate Report"):
                llm = LLMClient("gemini")
                if role_name == "Engineer":
                    # Engineering Persona
                    prompt = f"Act as Vibration Analyst. Subject: {brand} {model}. SNR {res['snr_db']:.1f} dB. Analyze harmonics and mechanical resonance."
                else:
                    # Management Persona
                    prompt = f"Act as QA Director. Subject: {brand} {model}. SNR {res['snr_db']:.1f} dB. Assess return risk and warranty liability."
                st.write(llm.complete(prompt))

    # --- TAB 3: LIFECYCLE ---
    with tabs[3]: 
        st.subheader(f"{role_name} Projection")
        horizon = st.slider("Days", 10, 90, 30)
        if st.button("Run Forecast"):
            f_res = forecast_with_uncertainty(payload, horizon)
            hist = f_res["history_used"]
            fc = f_res["mean_forecast"]
            events = find_signal_events(hist)
            df = pd.DataFrame({"Forecast": [None]*len(hist) + fc, "Historical": hist + [None]*len(fc)})
            st.line_chart(df)
            
            llm = LLMClient("gemini")
            if role_name == "Engineer":
                # Engineering Persona
                prompt = f"Act as Chemist. {brand} {model}. Drop at Index {events['steepest_drop_idx']}. Analyze degradation and lithium plating."
            else:
                # Management Persona
                prompt = f"Act as Warranty Manager. {brand} {model}. Predicted {fc[-1]:.1f}%. Assess financial risk."
            st.write(llm.complete(prompt))

    with tabs[4]: 
        runs = fetch_runs_for_device(sel_id)
        if not runs.empty:
            rid = st.selectbox("Run ID", runs['run_id'])
            chain = fetch_audit_chain(rid)
            st.dataframe(chain[["created_at", "event_type"]], use_container_width=True)
            for _, row in chain.iterrows():
                with st.expander(f"{row['event_type']} ({row['created_at']})"):
                    render_clean(row['payload_json'])

    if role_name == "Engineer":
        st.markdown("---")
        with st.expander("🔧 Data Dictionary"): st.write(payload)

st.sidebar.title("✅ NEURAL AUDIT")
role = st.sidebar.selectbox("Role", ["Management", "Engineer"])
show_device_dashboard(role)
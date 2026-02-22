# update_project.py
import os

# 1. APP.PY (Fixed: Sidebar at top, Executive Dashboard included)
app_code = r'''
from __future__ import annotations
import json
import hashlib
from typing import Any, Dict, Tuple
import pandas as pd
import streamlit as st

# --- IMPORTS ---
from orchestrator import Orchestrator
from db_access import (
    init_db_schema, list_devices, get_device_payload, count_devices,
    fetch_runs_for_device, fetch_audit_chain, fetch_recent_runs,
    fetch_tool_events_recent, compute_arbiter_risk_distribution,
    compute_uncertainty_trend, compute_missing_fields_rate
)
from db_persist import persist_run, persist_tool_event
from tools import run_fft_welch

# --- PAGE CONFIG ---
st.set_page_config(page_title="Device Passport Audit", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# --- SIDEBAR (MOVED TO TOP) ---
st.sidebar.title("Device Passport")
st.sidebar.markdown("---")
role = st.sidebar.selectbox("Select Role", ["Operator", "Engineering", "Executive"], index=0)
st.sidebar.caption(f"Current View: **{role}**")
st.sidebar.markdown("---")

# --- DB CHECK ---
try:
    init_db_schema()
except Exception as e:
    st.error(f"🛑 **Database Connection Failed**\n\n{e}")
    st.info("Check DP_DATABASE_URL and Docker.")
    st.stop()

# --- HELPERS ---
def _titleize(s): return s.replace("_", " ").strip().title()
def _to_dict(v): 
    if isinstance(v, str) and v.startswith("{"):
        try: return json.loads(v)
        except: return v
    return v

def _render_bullets(title, flags, icon="🔹"):
    st.markdown(f"### {title}")
    if not flags: st.info("No flags."); return
    for k, v in flags.items():
        val = "Yes" if v is True else "No" if v is False else str(v)
        ico = "✅" if v is True else "❌" if v is False else icon
        st.markdown(f"- {ico} **{_titleize(k)}**: {val}")

def _integrity(chain):
    if chain.empty: return 0,0
    ok, prev = 0, None
    for _, r in chain.iterrows():
        load = r.get("payload_json")
        if isinstance(load, str): load = json.loads(load)
        canon = json.dumps(load, sort_keys=True, separators=(",", ":"))
        base = f"{r.get('prev_hash') or prev or ''}|{str(r['event_type'])}|{canon}"
        if hashlib.sha256(base.encode()).hexdigest() == str(r['event_hash']): ok += 1
        prev = r['event_hash']
    return ok, len(chain)

# --- VIEWS ---
if role == "Operator":
    st.title("🎛️ Operator Dashboard")
    devs = list_devices(limit=500)
    if not devs: st.warning("No devices found."); st.stop()
    
    opts = {f"{d['device_id']} | {d.get('device_payload',{}).get('brand','?')}": d['device_id'] for d in devs}
    sel = st.selectbox("Select Device", list(opts.keys()))
    did = opts[sel]
    data = get_device_payload(did)

    t1, t2, t3, t4 = st.tabs(["Overview", "Audit", "Tools", "Chain"])
    
    with t1:
        c1, c2 = st.columns(2)
        with c1: _render_bullets("GDPR", _to_dict(data.get("gdpr_flags")), "🔐")
        with c2: _render_bullets("R2v3", _to_dict(data.get("r2v3_flags")), "♻️")
        with st.expander("Raw JSON"): st.json(data)

    with t2:
        st.subheader("Multi-Agent Audit")
        if st.button("🚀 Run Audit", type="primary"):
            with st.spinner("Auditing..."):
                res = Orchestrator().run_device_audit(data)
                persist_run(res["run_id"], did)
                st.session_state["last_run"] = res["run_id"]
            st.success(f"Done! ID: {res['run_id']}")
            c1, c2 = st.columns([3,1])
            c1.info(res.get("final_narrative"))
            c2.metric("Uncertainty", f"{res.get('final_uncertainty',0):.2f}")
        
        hist = fetch_runs_for_device(did)
        if not hist.empty: st.dataframe(hist[["created_at", "run_id"]])

    with t3:
        samps = data.get("fft_samples")
        if samps and st.button("Run Welch PSD"):
            if isinstance(samps, str): samps = json.loads(samps)
            mets = run_fft_welch(samps, float(data.get("fft_sample_rate_hz", 100)))
            st.success("Analysis Complete")
            c1, c2 = st.columns(2)
            c1.metric("Peak Hz", f"{mets['peak_freq_hz']:.1f}")
            c2.metric("SNR dB", f"{mets['snr_db']:.1f}")
            persist_tool_event(st.session_state.get("last_run","manual"), did, "fft", "welch", "1.0", "samples", mets, {}, 0.9, "success")

    with t4:
        runs = fetch_runs_for_device(did)
        if not runs.empty:
            rid = st.selectbox("Run ID", runs["run_id"].unique())
            chain = fetch_audit_chain(rid)
            ok, tot = _integrity(chain)
            st.caption(f"Integrity: {ok}/{tot} verified.")
            st.dataframe(chain[["event_type", "created_at", "payload_json"]])

elif role == "Engineering":
    st.title("🛠️ Engineering")
    days = st.slider("Days", 1, 90, 30)
    c1, c2, c3 = st.columns(3)
    c1.metric("Devices", count_devices())
    c2.metric("Recent Runs", len(fetch_recent_runs(1000, days)))
    c3.metric("Data Issues", f"{compute_missing_fields_rate(days)[2]*100:.1f}%")
    
    st.bar_chart(compute_arbiter_risk_distribution(days).set_index("arbiter_risk_rating"))
    st.line_chart(compute_uncertainty_trend(days).set_index("created_at")["final_uncertainty"])

elif role == "Executive":
    st.title("📊 Executive Dashboard")
    days = st.slider("Period", 7, 180, 30)
    runs = fetch_recent_runs(5000, days)
    risk = compute_arbiter_risk_distribution(days)
    
    high = risk[risk["arbiter_risk_rating"].isin(["High", "Critical"])]["count"].sum() if not risk.empty else 0
    pct = (high / len(runs) * 100) if not runs.empty else 0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Audits", len(runs))
    k2.metric("High Risk", high)
    k3.metric("Risk %", f"{pct:.1f}%")
    
    st.caption("Risk Profile")
    if not risk.empty: st.bar_chart(risk.set_index("arbiter_risk_rating")["count"])
'''

# 2. ORCHESTRATOR.PY
orch_code = r'''
import hashlib, datetime
from agent_r2v3 import AgentR2V3
from agent_gdpr import AgentGDPR
from agent_sensor import AgentSensorHealth
from verifier import VerificationModule
from arbiter import BlindArbiter
from meta_reviewer import MetaReviewer
from audit_logger import AuditLogger
from llm_client import verify_llm_provider_available

class Orchestrator:
    def __init__(self):
        verify_llm_provider_available()
        self.logger = AuditLogger("audit_logs")
        self.agents = {"R2v3": AgentR2V3(), "GDPR": AgentGDPR(), "Sensor": AgentSensorHealth()}
        self.verifier = VerificationModule()
        self.arbiter = BlindArbiter()
        self.meta = MetaReviewer()

    def run_device_audit(self, device):
        rid = f"run_{hashlib.sha256((datetime.datetime.utcnow().isoformat()+str(device.get('device_id'))).encode()).hexdigest()[:8]}"
        self.logger.start_new_run(rid, device.get("device_id"))

        # Round 1
        r1 = {n: a.round1(device) for n, a in self.agents.items()}
        for n, o in r1.items(): self.logger.log_section(f"R1-{n}", o)

        # Round 2
        anon = list(r1.values())
        r2 = {n: a.round2(anon) for n, a in self.agents.items()}
        for n, o in r2.items(): self.logger.log_section(f"R2-{n}", o)

        # Verification & Arbitration
        cove = self.verifier.verify(device, r1, r2)
        self.logger.log_section("COVE", cove)
        arb = self.arbiter.adjudicate(r1, r2, cove)
        self.logger.log_section("ARBITER", arb)

        # Meta Review
        meta = self.meta.review(arb, device, cove)
        self.logger.log_section("META", meta)

        rec = {
            "run_id": rid, "timestamp": datetime.datetime.utcnow().isoformat(),
            "final_narrative": meta.get("adjusted_narrative", arb["fused_narrative"]),
            "final_uncertainty": meta.get("final_uncertainty", arb["fused_uncertainty"]),
            "details": {"r1": r1, "r2": r2, "cove": cove, "arb": arb, "meta": meta}
        }
        self.logger.log_section("FINAL", rec)
        self.logger.end_run()
        return rec
'''

# 3. VERIFIER.PY
ver_code = r'''
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
'''

# 4. ARBITER.PY
arb_code = r'''
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
'''

# 5. AGENTS
ag_gdpr = r'''
import random
from llm_client import LLMClient
from tools import evaluate_gdpr_flags, evaluate_audit_trail
class AgentGDPR:
    def __init__(self): self.name="GDPR"; self.llm=LLMClient("gemini")
    def round1(self, dev):
        tools = {"gdpr": evaluate_gdpr_flags(dev), "audit": evaluate_audit_trail(dev)}
        txt = self.llm.complete(f"GDPR Audit {dev} {tools} fmt: NARRATIVE, RISK RATING, UNCERTAINTY")
        return {"agent":self.name, "round":1, "text":txt, "risk_rating":"Medium", "uncertainty":0.4, "tool_outputs":tools}
    def round2(self, ops):
        txt = self.llm.complete(f"Critique {ops}")
        return {"agent":self.name, "round":2, "text":txt, "updated_uncertainty":0.3}
'''

ag_r2 = r'''
import random
from llm_client import LLMClient
from tools import evaluate_r2v3_risk
class AgentR2V3:
    def __init__(self): self.name="R2v3"; self.llm=LLMClient("openai")
    def round1(self, dev):
        tools = {"r2": evaluate_r2v3_risk(dev)}
        txt = self.llm.complete(f"R2v3 Audit {dev} {tools} fmt: NARRATIVE, RISK RATING, UNCERTAINTY")
        return {"agent":self.name, "round":1, "text":txt, "risk_rating":"Medium", "uncertainty":0.5, "tool_outputs":tools}
    def round2(self, ops):
        txt = self.llm.complete(f"Critique {ops}")
        return {"agent":self.name, "round":2, "text":txt, "updated_uncertainty":0.4}
'''

ag_sens = r'''
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
'''

# WRITE FILES
files = {
    "app.py": app_code,
    "orchestrator.py": orch_code,
    "verifier.py": ver_code,
    "arbiter.py": arb_code,
    "agent_gdpr.py": ag_gdpr,
    "agent_r2v3.py": ag_r2,
    "agent_sensor.py": ag_sens
}

print("Overwriting local files with corrected versions...")
for name, content in files.items():
    with open(name, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"✅ Updated {name}")
print("Done. You can now run 'streamlit run app.py'")
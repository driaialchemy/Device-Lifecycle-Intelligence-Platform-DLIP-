import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from db_access import (
    compute_arbiter_risk_distribution,
    count_devices,
    fetch_audit_events,
    fetch_audit_chain,
    fetch_recent_runs,
    fetch_recent_runs_with_event_counts,
    fetch_runs_for_device,
    get_device_payload,
    init_db_schema,
    list_devices,
)
from db_persist import persist_audit_result, persist_run
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


def device_posture_dataframe(devices: list[dict], runs: pd.DataFrame | None = None) -> pd.DataFrame:
    run_counts = {}
    if runs is not None and not runs.empty and "device_id" in runs.columns:
        run_counts = runs["device_id"].value_counts().to_dict()

    rows = []
    for device in devices:
        payload = device.get("device_payload") or {}
        gdpr_flags = payload.get("gdpr_flags") or {}
        r2v3_flags = payload.get("r2v3_flags") or {}

        gdpr_risks = sum(
            1
            for key in ("residual_identifiers_found", "account_tokens_present", "paired_phone_id_present")
            if gdpr_flags.get(key) is True
        )
        r2v3_risks = sum(
            1
            for key in ("tamper_seal_broken", "mdm_profile_present", "residual_personal_data_risk", "unofficial_firmware")
            if r2v3_flags.get(key) is True
        )
        if r2v3_flags.get("factory_reset_verified") is False:
            r2v3_risks += 1

        risk_signals = gdpr_risks + r2v3_risks
        if risk_signals >= 4:
            risk_band = "High"
        elif risk_signals >= 2:
            risk_band = "Medium"
        elif risk_signals == 1:
            risk_band = "Watch"
        else:
            risk_band = "Low"

        rows.append(
            {
                "device_id": device.get("device_id"),
                "brand": payload.get("brand"),
                "model": payload.get("model"),
                "region": payload.get("region"),
                "risk_band": risk_band,
                "risk_signals": risk_signals,
                "gdpr_risk_signals": gdpr_risks,
                "r2v3_risk_signals": r2v3_risks,
                "audit_runs": int(run_counts.get(device.get("device_id"), 0)),
                "factory_reset_verified": r2v3_flags.get("factory_reset_verified"),
                "sensor_suite": payload.get("sensor_suite"),
            }
        )
    return pd.DataFrame(rows)


def data_quality_dataframe(devices: list[dict]) -> pd.DataFrame:
    required_payload_fields = ["brand", "model", "serial_number", "firmware_version", "region"]
    rows = []
    for device in devices:
        payload = device.get("device_payload") or {}
        missing = [
            field
            for field in required_payload_fields
            if payload.get(field) in (None, "", [], {})
        ]
        rows.append(
            {
                "device_id": device.get("device_id"),
                "missing_fields": ", ".join(missing) if missing else "None",
                "has_gdpr_flags": bool(payload.get("gdpr_flags")),
                "has_r2v3_flags": bool(payload.get("r2v3_flags")),
                "has_serial": bool(payload.get("serial_number")),
            }
        )
    return pd.DataFrame(rows)


def audit_run_dataframe(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if runs.empty:
        return pd.DataFrame()

    final_events = {}
    if not events.empty:
        for _, row in events[events["event_type"] == "FINAL"].iterrows():
            final_events.setdefault(row.get("run_id"), row.get("payload_json") or {})

    rows = []
    for _, run in runs.iterrows():
        final_payload = final_events.get(run.get("run_id"), {})
        rows.append(
            {
                "run_id": run.get("run_id"),
                "device_id": run.get("device_id"),
                "created_at": run.get("created_at"),
                "structured_events": int(run.get("audit_events", 0) or 0),
                "arbiter_risk_rating": final_payload.get("arbiter_risk_rating", "Not captured"),
                "final_uncertainty": final_payload.get("final_uncertainty"),
                "status": "Structured" if final_payload else "Run record only",
            }
        )
    return pd.DataFrame(rows)


def audit_artifacts_dataframe() -> pd.DataFrame:
    log_dir = Path("audit_logs")
    if not log_dir.exists():
        return pd.DataFrame(columns=["artifact", "size_kb", "modified"])

    rows = []
    for path in sorted(log_dir.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        rows.append(
            {
                "artifact": path.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": pd.to_datetime(stat.st_mtime, unit="s"),
            }
        )
    return pd.DataFrame(rows)


def latest_final_payload(events: pd.DataFrame) -> dict:
    if events.empty:
        return {}
    finals = events[events["event_type"] == "FINAL"]
    if finals.empty:
        return {}
    payload = finals.iloc[0].get("payload_json")
    return payload if isinstance(payload, dict) else {}


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
                    persist_audit_result(result, device_id)
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
    st.info("Operational view for registry health, data quality, audit coverage, and traceability.")

    devices = list_devices(limit=1000)
    runs = fetch_recent_runs_with_event_counts(limit=200)
    events = fetch_audit_events(limit=500)
    posture = device_posture_dataframe(devices, runs)
    quality = data_quality_dataframe(devices)
    audit_runs = audit_run_dataframe(runs, events)
    artifacts = audit_artifacts_dataframe()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registry Devices", len(devices))
    c2.metric("Audit Runs", 0 if runs.empty else len(runs))
    c3.metric("Structured Events", 0 if events.empty else len(events))
    c4.metric("Local Audit Files", 0 if artifacts.empty else len(artifacts))

    tab_registry, tab_quality, tab_audits, tab_artifacts = st.tabs(
        ["Registry", "Data Quality", "Audit Operations", "Artifacts"]
    )

    with tab_registry:
        st.subheader("Device Registry And Risk Signals")
        if posture.empty:
            st.warning("No devices found in device_registry. Run the seed script.")
        else:
            st.dataframe(posture, use_container_width=True)
            brand_summary = (
                posture.groupby("brand", dropna=False)["risk_signals"]
                .sum()
                .reset_index()
                .sort_values("risk_signals", ascending=False)
            )
            st.markdown("#### Risk Signals By Brand")
            st.bar_chart(brand_summary.set_index("brand"))

    with tab_quality:
        st.subheader("Registry Completeness")
        if quality.empty:
            st.info("No registry rows to validate.")
        else:
            missing_rows = quality[quality["missing_fields"] != "None"]
            q1, q2, q3 = st.columns(3)
            q1.metric("Rows Missing Required Fields", len(missing_rows))
            q2.metric("Rows With GDPR Flags", int(quality["has_gdpr_flags"].sum()))
            q3.metric("Rows With R2v3 Flags", int(quality["has_r2v3_flags"].sum()))
            st.dataframe(quality, use_container_width=True)

    with tab_audits:
        st.subheader("Audit Run Health")
        if audit_runs.empty:
            st.info("No audit runs yet. Start an audit from the Operator view.")
        else:
            st.dataframe(audit_runs, use_container_width=True)
            if "status" in audit_runs:
                status_counts = audit_runs["status"].value_counts().rename_axis("status").reset_index(name="count")
                st.markdown("#### Structured Capture Status")
                st.bar_chart(status_counts.set_index("status"))

        if not events.empty:
            st.markdown("#### Recent Structured Audit Events")
            event_preview = events[["created_at", "run_id", "event_type"]].head(25)
            st.dataframe(event_preview, use_container_width=True)

    with tab_artifacts:
        st.subheader("Local Audit Artifacts")
        st.caption("Plain-text hash-chained audit files written by the orchestrator.")
        if artifacts.empty:
            st.info("No local audit files found.")
        else:
            st.dataframe(artifacts, use_container_width=True)


# === EXECUTIVE VIEW ===
elif role == "Executive":
    st.title("📊 Executive Dashboard")
    st.caption("Portfolio-level compliance posture and audit coverage.")

    devices = list_devices(limit=1000)
    runs = fetch_recent_runs_with_event_counts(limit=500)
    events = fetch_audit_events(limit=1000)
    posture = device_posture_dataframe(devices, runs)
    audit_runs = audit_run_dataframe(runs, events)
    risk_dist = compute_arbiter_risk_distribution(days=30)
    latest_final = latest_final_payload(events)

    total_devices = len(devices)
    audited_devices = 0 if runs.empty else runs["device_id"].nunique()
    audit_coverage = 0 if total_devices == 0 else int((audited_devices / total_devices) * 100)
    open_risk_signals = 0 if posture.empty else int(posture["risk_signals"].sum())
    high_or_medium = 0 if posture.empty else int(posture["risk_band"].isin(["High", "Medium"]).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devices In Registry", total_devices)
    c2.metric("Audit Coverage", f"{audit_coverage}%")
    c3.metric("Audit Runs", 0 if runs.empty else len(runs))
    c4.metric("Open Risk Signals", open_risk_signals)

    left, right = st.columns(2)
    with left:
        st.subheader("Portfolio Risk Bands")
        if posture.empty:
            st.info("No device registry data available.")
        else:
            band_counts = posture["risk_band"].value_counts().rename_axis("risk_band").reset_index(name="devices")
            st.bar_chart(band_counts.set_index("risk_band"))

    with right:
        st.subheader("Risk Signals By Brand")
        if posture.empty:
            st.info("No device registry data available.")
        else:
            brand_risk = (
                posture.groupby("brand", dropna=False)["risk_signals"]
                .sum()
                .reset_index()
                .sort_values("risk_signals", ascending=False)
            )
            st.bar_chart(brand_risk.set_index("brand"))

    st.subheader("Audit Outcomes")
    if not risk_dist.empty:
        st.bar_chart(risk_dist.set_index("arbiter_risk_rating"))
    elif not audit_runs.empty:
        st.info("Audit runs exist, but older runs did not capture structured arbiter outcomes. Future audits will populate this chart.")
    else:
        st.info("No audit runs yet. Run an audit from the Operator view to populate outcomes.")

    if latest_final:
        st.subheader("Latest Board Consensus")
        latest_cols = st.columns(3)
        latest_cols[0].metric("Risk Rating", latest_final.get("arbiter_risk_rating", "Unknown"))
        uncertainty = latest_final.get("final_uncertainty")
        latest_cols[1].metric("Uncertainty", f"{uncertainty:.2f}" if isinstance(uncertainty, (int, float)) else "Unknown")
        latest_cols[2].metric("High/Medium Devices", high_or_medium)
        st.info(latest_final.get("final_narrative", "No final narrative captured."))

    st.subheader("Devices Needing Attention")
    if posture.empty:
        st.info("No device registry data available.")
    else:
        attention = posture[posture["risk_signals"] > 0].sort_values(
            ["risk_signals", "audit_runs"], ascending=[False, True]
        )
        if attention.empty:
            st.success("No open registry risk signals across the device portfolio.")
        else:
            st.dataframe(
                attention[["device_id", "brand", "model", "risk_band", "risk_signals", "audit_runs"]],
                use_container_width=True,
            )

    st.subheader("Recent Audit Activity")
    if audit_runs.empty:
        st.info("No audit run activity yet.")
    else:
        st.dataframe(audit_runs.head(20), use_container_width=True)

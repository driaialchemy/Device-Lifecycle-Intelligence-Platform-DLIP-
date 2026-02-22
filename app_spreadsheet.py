# app_spreadsheet.py
# Spreadsheet-driven Multi-Agent Audit UI

import streamlit as st
import pandas as pd
from pathlib import Path
from orchestrator import Orchestrator

def load_spreadsheet(file_or_path):
    if not file_or_path: return None
    if isinstance(file_or_path, (str, Path)):
        return pd.read_excel(file_or_path) if str(file_or_path).endswith("xlsx") else pd.read_csv(file_or_path)
    return pd.read_csv(file_or_path) if file_or_path.name.endswith(".csv") else pd.read_excel(file_or_path)

def main():
    st.set_page_config(page_title="Spreadsheet Audit", layout="wide")
    st.title("📂 Batch Audit (Spreadsheet)")

    uploaded = st.file_uploader("Upload .xlsx / .csv", type=["xlsx", "csv"])
    if not uploaded:
        st.info("Upload a file to begin.")
        return

    try:
        df = load_spreadsheet(uploaded)
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return

    st.dataframe(df.head())
    
    if "device_id" not in df.columns:
        st.error("Spreadsheet must have 'device_id' column")
        return

    selected_id = st.selectbox("Select Device ID", df["device_id"].astype(str).unique())

    if st.button("Run Audit"):
        row = df[df["device_id"].astype(str) == str(selected_id)].iloc[0].to_dict()
        
        # Clean NaNs
        device_dict = {k: v for k, v in row.items() if pd.notna(v)}
        
        orch = Orchestrator()
        with st.spinner("Running Multi-Agent Audit..."):
            res = orch.run_device_audit(device_dict)
            
        st.success(f"Run {res['run_id']} Complete")
        st.subheader("Final Narrative")
        st.markdown(res["final_narrative"])
        st.metric("Uncertainty", f"{res['final_uncertainty']:.2f}")

if __name__ == "__main__":
    main()
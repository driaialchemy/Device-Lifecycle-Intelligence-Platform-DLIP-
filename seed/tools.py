from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import welch

from db_access import fetch_sensor_series, fetch_battery_history


def fft_welch_from_db(
    device_id: str,
    sensor: str = "accelerometer_mag",
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
    nperseg: int = 256,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    df = fetch_sensor_series(device_id=device_id, sensor=sensor)
    if df.empty:
        raise ValueError("No sensor data for device.")

    if start_ts:
        df = df[df["ts"] >= pd.to_datetime(start_ts, utc=True)]
    if end_ts:
        df = df[df["ts"] <= pd.to_datetime(end_ts, utc=True)]

    if df.empty:
        raise ValueError("No sensor data in selected window.")

    deltas = df["ts"].diff().dt.total_seconds().dropna()
    dt = float(deltas.median()) if len(deltas) else 0.0
    fs = (1.0 / dt) if dt > 0 else 0.0
    if fs <= 0:
        raise ValueError("Cannot estimate sample rate from timestamps.")

    x = df["value"].to_numpy(dtype=float)
    nperseg = int(min(nperseg, len(x)))
    freqs, psd = welch(x, fs=fs, nperseg=nperseg)

    dom = float(freqs[0]) if len(freqs) else 0.0
    if len(freqs) > 1:
        dom = float(freqs[int(np.argmax(psd[1:]) + 1)])

    def bandpower(lo: float, hi: float) -> float:
        m = (freqs >= lo) & (freqs < hi)
        if not np.any(m):
            return 0.0
        return float(np.trapz(psd[m], freqs[m]))

    metrics = {
        "fft_method": "welch",
        "sensor": sensor,
        "sample_rate_hz_est": float(fs),
        "n_samples": int(len(x)),
        "nperseg": int(nperseg),
        "dominant_freq_hz": float(dom),
        "bandpower_0_3hz": bandpower(0.0, 3.0),
        "bandpower_3_10hz": bandpower(3.0, 10.0),
        "noise_floor": float(np.median(psd)) if len(psd) else 0.0,
        "psd_summary": {
            "freq_min": float(freqs.min()) if len(freqs) else 0.0,
            "freq_max": float(freqs.max()) if len(freqs) else 0.0,
            "psd_min": float(psd.min()) if len(psd) else 0.0,
            "psd_max": float(psd.max()) if len(psd) else 0.0,
        },
    }
    return freqs, psd, metrics

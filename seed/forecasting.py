from __future__ import annotations
from typing import Any, Dict
import numpy as np

def forecast_linear(history: np.ndarray, horizon: int) -> Dict[str, Any]:
    y = history.astype(float)
    x = np.arange(len(y), dtype=float)
    A = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    x_f = np.arange(len(y), len(y) + horizon, dtype=float)
    y_f = a + b * x_f
    resid = y - (a + b * x)
    sigma = float(np.std(resid)) if len(resid) > 2 else 0.5
    return {"a": a, "b": b, "sigma": sigma, "forecast": y_f}

def forecast_neural_operator_like(history: np.ndarray, horizon: int, modes: int = 16) -> Dict[str, Any]:
    y = history.astype(float)
    y = (y - y.mean()) / (y.std() + 1e-9)
    if len(y) < 20:
        lin = forecast_linear(y, horizon)
        return {"note": "fallback_linear_due_to_short_series", "modes": modes, "forecast": lin["forecast"]}

    X, Y = [], []
    for t in range(len(y) - 1):
        w = y[max(0, t - 31) : t + 1]
        if len(w) < 32:
            w = np.pad(w, (32 - len(w), 0))
        fft = np.fft.rfft(w)
        feat = np.concatenate([fft.real[:modes], fft.imag[:modes]])
        X.append(feat)
        Y.append(y[t + 1])
    X = np.vstack(X)
    Y = np.asarray(Y)

    lam = 1e-2
    w = np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ Y)

    seq = y.tolist()
    for _ in range(horizon):
        wdw = np.asarray(seq[-32:], dtype=float)
        fft = np.fft.rfft(wdw)
        feat = np.concatenate([fft.real[:modes], fft.imag[:modes]])
        seq.append(float(feat @ w))

    return {"modes": int(modes), "lambda": lam, "forecast": np.asarray(seq[-horizon:])}

def forecast_with_uncertainty(history: np.ndarray, horizon: int) -> Dict[str, Any]:
    lin = forecast_linear(history, horizon)
    fno = forecast_neural_operator_like(history, horizon)
    y_lin = np.asarray(lin["forecast"], dtype=float)
    y_fno = np.asarray(fno["forecast"], dtype=float)

    y_ens = 0.6 * y_lin + 0.4 * y_fno
    sigma = float(lin.get("sigma", 0.5))
    unc = sigma + 0.5 * np.abs(y_lin - y_fno)

    return {
        "linear": {"slope": float(lin["b"]), "sigma": sigma, "forecast": y_lin.tolist()},
        "neural_operator_like": {"modes": fno.get("modes"), "forecast": y_fno.tolist()},
        "ensemble": {"forecast": y_ens.tolist(), "uncertainty": unc.tolist()},
    }

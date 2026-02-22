# seed_manager.py
# Ensures deterministic behavior across Python, NumPy, and agent processes.

import os
import random
import numpy as np

# Optional: PyTorch determinism if forecasting models rely on torch
try:
    import torch  # type: ignore
    TORCH_AVAILABLE = True
except Exception:
    # Important: torch can be installed but fail to initialize on Windows (DLL errors).
    TORCH_AVAILABLE = False
    torch = None  # type: ignore


def set_global_seed(seed: int = 42):
    """
    Establishes deterministic operation for all components.
    Called by the Orchestrator during initialization.

    Determinism is crucial for audit reproducibility in compliance contexts.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)

    random.seed(seed)
    np.random.seed(seed)

    if TORCH_AVAILABLE and torch is not None:
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

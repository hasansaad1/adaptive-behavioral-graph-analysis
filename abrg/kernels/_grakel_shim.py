"""GraKeL import shim for NumPy 2.x (ComplexWarning moved)."""

from __future__ import annotations

import numpy as np

if not hasattr(np, "ComplexWarning"):
    try:
        from numpy.exceptions import ComplexWarning as _CW
    except ImportError:  # pragma: no cover

        class _CW(Warning):
            pass

    np.ComplexWarning = _CW  # type: ignore[attr-defined]

from grakel import Graph  # noqa: E402
from grakel.kernels import Propagation, ShortestPath, WeisfeilerLehman  # noqa: E402

__all__ = ["Graph", "WeisfeilerLehman", "Propagation", "ShortestPath"]

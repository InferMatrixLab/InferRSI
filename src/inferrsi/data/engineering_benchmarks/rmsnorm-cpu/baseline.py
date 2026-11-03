"""NumPy CPU adaptation of the attributed KernelBench task; see LICENSE."""

import numpy as np


def compute(x, *, eps):
    rms = np.sqrt(np.mean(x * x, axis=1, keepdims=True) + np.float32(eps))
    return x / rms

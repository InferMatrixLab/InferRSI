"""NumPy CPU adaptation of the attributed KernelBench task; see LICENSE."""

import numpy as np


def compute(x, *, eps):
    values = np.exp(x - np.max(x, axis=1, keepdims=True))
    return values / np.sum(values, axis=1, keepdims=True)

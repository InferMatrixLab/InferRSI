"""Reviewed example using temporary buffers; not an agent-generated result."""

import numpy as np


def compute(x, *, eps):
    squared = np.square(x)
    rms = np.mean(squared, axis=1, keepdims=True)
    rms += np.float32(eps)
    np.sqrt(rms, out=rms)
    return np.divide(x, rms)

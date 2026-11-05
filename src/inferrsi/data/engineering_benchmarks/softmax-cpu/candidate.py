"""Reviewed example using temporary buffers; not an agent-generated result."""

import numpy as np


def compute(x, *, eps):
    output = np.subtract(x, np.max(x, axis=1, keepdims=True))
    np.exp(output, out=output)
    output /= np.sum(output, axis=1, keepdims=True)
    return output

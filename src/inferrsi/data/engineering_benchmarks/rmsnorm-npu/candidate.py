"""Authored reference optimization, not an Agent/skill efficacy result."""

import torch_npu


def compute(x, weight, *, eps):
    return torch_npu.npu_rms_norm(x, weight, epsilon=eps)[0]

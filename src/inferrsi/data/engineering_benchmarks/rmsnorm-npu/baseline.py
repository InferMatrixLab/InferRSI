"""Eager affine RMSNorm baseline; all arithmetic executes on the input NPU."""

import torch


def compute(x, weight, *, eps):
    return x * torch.rsqrt(torch.mean(x * x, dim=-1, keepdim=True) + eps) * weight

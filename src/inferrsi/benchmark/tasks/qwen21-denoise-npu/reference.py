# SPDX-License-Identifier: Apache-2.0
"""Independent FP32 reference: recompute the joint sequence at every step."""

import math

import torch
import torch.nn.functional as F


def compute(latents, text, text_mask, sigmas, positions, params, *, config):
    batch, targets, _ = latents.shape
    prefix = text.shape[1]
    width, heads = config["hidden"], config["heads"]
    dim = width // heads
    eps = config["eps"]
    original_dtype = latents.dtype
    current = latents.float()
    text = text.float()

    def project(value, weight):
        return value @ weight.float().T

    def norm(value):
        centered = value - value.mean(-1, keepdim=True)
        return centered / (centered.square().mean(-1, keepdim=True) + eps).sqrt()

    def rms(value, weight):
        return value / (value.square().mean(-1, keepdim=True) + eps).sqrt() * weight.float()

    angle_parts = []
    offset = 0
    for axis, axis_dim in enumerate(config["axes_dims"]):
        frequencies = params["rope_frequencies"][offset : offset + axis_dim // 2].float()
        angle_parts.append(positions[:, axis : axis + 1].float() * frequencies)
        offset += axis_dim // 2
    angles = torch.cat(angle_parts, dim=-1)
    rotation = torch.stack((angles.cos(), angles.sin()), dim=-1)[None, :, None]

    def rotate(value):
        even, odd = value[..., ::2], value[..., 1::2]
        result = torch.empty_like(value)
        result[..., ::2] = even * rotation[..., 0] - odd * rotation[..., 1]
        result[..., 1::2] = odd * rotation[..., 0] + even * rotation[..., 1]
        return result

    normalized_text = rms(text, params["text_norm"].float() + 1)
    conditioned = project(
        F.gelu(project(normalized_text, params["text_in"]), approximate="tanh"), params["text_out"]
    )
    valid = torch.cat((text_mask, text_mask.new_ones(batch, targets)), dim=1)
    allowed = valid[:, None, None].expand(batch, 1, prefix + targets, prefix + targets).clone()
    allowed[:, :, :prefix, prefix:] = False
    history = []
    for sigma, next_sigma in zip(sigmas[:-1], sigmas[1:]):
        value = torch.cat((conditioned, project(current, params["image_in"])), dim=1)
        times = torch.stack((sigma, sigma.new_zeros(()))).to(original_dtype).float()
        phase = times[:, None] * 1000 * params["time_frequencies"].float()
        features = torch.cat((phase.cos(), phase.sin()), dim=-1)
        embedding = project(F.silu(project(features, params["time_in"])), params["time_out"])
        mod = project(F.silu(embedding), params["modulation"])
        target_mod, prefix_mod = mod[0], mod[1]
        per_token = torch.cat((prefix_mod.expand(prefix, -1), target_mod.expand(targets, -1)))
        scale1, gate1, scale2, gate2 = per_token.chunk(4, dim=-1)
        for block in params["blocks"]:
            qkv = project(norm(value) * (1 + scale1), block["qkv"])
            query, key, projected = qkv.reshape(batch, -1, 3, heads, dim).unbind(2)
            query = rotate(rms(query, block["q_norm"]))
            key = rotate(rms(key, block["k_norm"]))
            logits = query.transpose(1, 2) @ key.transpose(1, 2).transpose(-1, -2)
            logits = (logits / math.sqrt(dim)).masked_fill(~allowed, -torch.inf)
            attended = (logits.softmax(-1) @ projected.transpose(1, 2)).transpose(1, 2)
            value = value + gate1.tanh() * project(
                attended.reshape(batch, -1, width), block["attention_out"]
            )
            normalized = norm(value) * (1 + scale2)
            gate = project(normalized, block["gate"])
            up = project(normalized, block["up"])
            value = value + gate2.tanh() * project(F.silu(gate) * up, block["down"])
        scale = project(F.silu(embedding[0]), params["final_scale"])
        prediction = project(norm(value[:, -targets:]) * (1 + scale), params["image_out"])
        current = (current + (next_sigma - sigma) * prediction).to(original_dtype).float()
        history.append(current.clone())
    return torch.stack(history)

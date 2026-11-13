# SPDX-License-Identifier: Apache-2.0
"""Scaled Qwen-Image 2.1 pre-optimization denoiser, using ordinary PyTorch."""

import torch
import torch.nn.functional as F


def _rms(x, weight, eps, zero_center=False):
    value = x.float()
    scale = weight.float() + 1 if zero_center else weight.float()
    return (value * torch.rsqrt(value.square().mean(-1, keepdim=True) + eps) * scale).to(x.dtype)


def _time(timesteps, params, dtype):
    angles = timesteps.float()[:, None] * 1000 * params["time_frequencies"]
    value = torch.cat((angles.cos(), angles.sin()), dim=-1).to(dtype)
    return F.linear(F.silu(F.linear(value, params["time_in"])), params["time_out"])


def _rotate(x, angles):
    pairs = x.float().unflatten(-1, (-1, 2))
    real, imag = pairs.unbind(-1)
    cosine = angles.cos()[None, :, None, :]
    sine = angles.sin()[None, :, None, :]
    return (
        torch.stack((real * cosine - imag * sine, real * sine + imag * cosine), -1)
        .flatten(-2)
        .to(x.dtype)
    )


def _rows(value, target, batch):
    return torch.where(target[None, :, None], value[:batch, None], value[batch:, None])


def compute(latents, text, text_mask, sigmas, positions, params, *, config):
    """Return every updated latent, with shape [steps, batch, target_tokens, channels]."""
    batch, target_tokens, _ = latents.shape
    prefix_tokens = text.shape[1]
    hidden = config["hidden"]
    heads = config["heads"]
    head_dim = hidden // heads
    eps = config["eps"]
    cache = []
    trajectory = []
    current = latents
    for step in range(sigmas.numel() - 1):
        # The original entry projects conditioning before sequence preparation,
        # even when decode subsequently uses the already cached prefix K/V.
        prefix = _rms(text, params["text_norm"], eps, zero_center=True)
        prefix = F.linear(
            F.gelu(F.linear(prefix, params["text_in"]), approximate="tanh"), params["text_out"]
        )
        target = F.linear(current, params["image_in"])
        value = torch.cat((prefix, target), dim=1) if step == 0 else target
        target_rows = torch.arange(value.shape[1], device=latents.device) >= (
            prefix_tokens if step == 0 else 0
        )
        timestep = torch.cat((sigmas[step].expand(batch), sigmas.new_zeros(batch))).to(
            latents.dtype
        )
        embedding = _time(timestep, params, latents.dtype)
        modulation = F.linear(F.silu(embedding), params["modulation"])
        angles = positions.index_select(1, params["rope_axes"]) * params["rope_frequencies"]
        if step:
            angles = angles[prefix_tokens:]
        key_valid = torch.cat((text_mask, text_mask.new_ones(batch, target_tokens)), dim=1)
        attention_mask = key_valid[:, None, None, :]
        if step == 0:
            visible = torch.ones(
                value.shape[1], value.shape[1], dtype=torch.bool, device=latents.device
            )
            visible[:prefix_tokens, prefix_tokens:] = False
            attention_mask = attention_mask & visible[None, None]
        for index, block in enumerate(params["blocks"]):
            scale1, gate1, scale2, gate2 = modulation.chunk(4, dim=-1)
            normalized = F.layer_norm(value, (hidden,), eps=eps)
            normalized = normalized * (1 + _rows(scale1, target_rows, batch))
            qkv = F.linear(normalized, block["qkv"]).view(batch, -1, 3, heads, head_dim)
            query, key, projected = qkv.unbind(2)
            query = _rotate(_rms(query, block["q_norm"], eps), angles)
            key = _rotate(_rms(key, block["k_norm"], eps), angles)
            if step == 0:
                cache.append((key[:, :prefix_tokens].clone(), projected[:, :prefix_tokens].clone()))
            else:
                key = torch.cat((cache[index][0], key), dim=1)
                projected = torch.cat((cache[index][1], projected), dim=1)
            attended = (
                F.scaled_dot_product_attention(
                    query.transpose(1, 2),
                    key.transpose(1, 2),
                    projected.transpose(1, 2),
                    attn_mask=attention_mask,
                )
                .transpose(1, 2)
                .reshape(batch, -1, hidden)
            )
            value = value + _rows(gate1, target_rows, batch).tanh() * F.linear(
                attended, block["attention_out"]
            )
            normalized = F.layer_norm(value, (hidden,), eps=eps)
            normalized = normalized * (1 + _rows(scale2, target_rows, batch))
            # Separate gate/up projections are present in the original source.
            mlp = F.silu(F.linear(normalized, block["gate"])) * F.linear(normalized, block["up"])
            value = value + _rows(gate2, target_rows, batch).tanh() * F.linear(mlp, block["down"])
        target = value[:, -target_tokens:]
        scale = F.linear(F.silu(embedding[:batch]), params["final_scale"])
        target = F.layer_norm(target, (hidden,), eps=eps) * (1 + scale[:, None])
        velocity = F.linear(target, params["image_out"])
        current = (current.float() + (sigmas[step + 1] - sigmas[step]) * velocity.float()).to(
            latents.dtype
        )
        trajectory.append(current)
    return torch.stack(trajectory)

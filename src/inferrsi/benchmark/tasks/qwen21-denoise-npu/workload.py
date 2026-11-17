# SPDX-License-Identifier: Apache-2.0
"""Small deterministic inputs and weights, with no model downloads."""

import math

import torch


def parameters(case, seed, device, dtype):
    generator = torch.Generator().manual_seed(seed)
    width = case["hidden"]
    dim = width // case["heads"]

    def weight(rows, columns):
        return (torch.randn(rows, columns, generator=generator) * (0.5 / math.sqrt(columns))).to(
            device=device, dtype=dtype
        )

    params = {
        "text_norm": (torch.randn(case["context_dim"], generator=generator) * 0.02).to(
            device=device, dtype=dtype
        ),
        "text_in": weight(width, case["context_dim"]),
        "text_out": weight(width, width),
        "image_in": weight(width, case["channels"]),
        "image_out": weight(case["channels"], width),
        "time_in": weight(width, case["time_dim"]),
        "time_out": weight(width, width),
        "modulation": weight(4 * width, width),
        "final_scale": weight(width, width),
        "time_frequencies": torch.exp(
            -math.log(10000)
            * torch.arange(case["time_dim"] // 2, dtype=torch.float32)
            / (case["time_dim"] // 2)
        ).to(device),
        "rope_axes": torch.repeat_interleave(
            torch.arange(3), torch.tensor([size // 2 for size in case["axes_dims"]])
        ).to(device),
        "rope_frequencies": torch.cat(
            [10000 ** (-torch.arange(0, size, 2).float() / size) for size in case["axes_dims"]]
        ).to(device),
    }
    params["blocks"] = [
        {
            "qkv": weight(3 * width, width),
            "attention_out": weight(width, width),
            "q_norm": torch.ones(dim, device=device, dtype=dtype),
            "k_norm": torch.ones(dim, device=device, dtype=dtype),
            "gate": weight(case["intermediate"], width),
            "up": weight(case["intermediate"], width),
            "down": weight(width, case["intermediate"]),
        }
        for _ in range(case["layers"])
    ]
    return params


def inputs(case, seed, device, dtype):
    generator = torch.Generator().manual_seed(seed)
    tokens = case["height"] * case["width"]
    batch, prefix = case["batch"], case["prefix"]
    latents = torch.randn(batch, tokens, case["channels"], generator=generator) * 0.5
    text = torch.randn(batch, prefix, case["context_dim"], generator=generator)
    mask = torch.ones(batch, prefix, dtype=torch.bool)
    for row in range(batch):
        mask[row, max(1, prefix - row * 3) :] = False
    text_positions = torch.arange(prefix).float()[:, None].expand(prefix, 3)
    y, x = torch.meshgrid(torch.arange(case["height"]), torch.arange(case["width"]), indexing="ij")
    image_positions = torch.stack(
        (torch.full_like(y, prefix), y - case["height"] // 2, x - case["width"] // 2), -1
    )
    positions = torch.cat((text_positions, image_positions.reshape(-1, 3)), dim=0)
    sigmas = torch.tensor(case["sigmas"], dtype=torch.float32)
    return (
        latents.to(device=device, dtype=dtype),
        text.to(device=device, dtype=dtype),
        mask.to(device),
        sigmas.to(device),
        positions.to(device),
    )


def map_tensors(value, transform):
    if isinstance(value, torch.Tensor):
        return transform(value)
    if isinstance(value, dict):
        return {key: map_tensors(item, transform) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(map_tensors(item, transform) for item in value)
    return value

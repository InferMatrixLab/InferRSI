# Shared by rounds 3-4: each layer visit of a decode step (B=1, L=1) runs as pre graph -> cache write + attention -> post graph.
# pre : residual read-in, message gates, norms, q/k/v/r/gate/sink projections, short convs, clips, relative bias; one compiled graph;
# mid : KV-cache write and attention (length changes every step, not compiled);
# post: output gate, o_proj, convs, residual, MoE, convs; one compiled graph. Conv states are explicit inputs/outputs.
# Options: mask_kernel = attention mask in one Metal kernel; fuse_proj = projections sharing an input in one quantized matmul.
import mlx.core as mx
from mlx import nn
from mlx_lm.models.inkling2 import layers as L
from mlx_lm.models.cache import RotatingKVCache

OPTS = dict(mask_kernel=False, fuse_proj=False, fuse_all6=False, fuse_msg=False, conv_ew=False)
_DEF = dict(OPTS)
_orig = L.DecoderLayer.__call__
_cache = {}
_fused = {}


def _sliding(self):
    return isinstance(self, L.SlidingDecoderLayer)


def _proj(self, attn, qi, ki, vi, same_kv):
    if OPTS["fuse_proj"]:
        f = _fused.get(id(attn))
        if f is not None:
            outs = f["qrgs"](qi)
            qp, rp, gate, sinks = mx.split(outs, f["qrgs_split"], axis=-1)
            if same_kv and OPTS["fuse_all6"]:  # sliding layer, no messages: q/k/v share the input, six projections at once
                qp, kp, vp, rp, gate, sinks = mx.split(f["all6"](qi), f["all6_split"], axis=-1)
                return qp, kp, vp, rp, gate, sinks
            kp = attn.k_proj(ki); vp = attn.v_proj(vi)
            return qp, kp, vp, rp, gate, sinks
    return attn.q_proj(qi), attn.k_proj(ki), attn.v_proj(vi), attn.r_proj(qi), attn.gate_proj(qi), attn.sink_proj(qi)


def _pre(self, has_bs, has_msg):
    sliding = _sliding(self); attn = self.self_attn

    def body(*args):
        it = iter(args)
        h = next(it); bs = next(it) if has_bs else None
        cs0 = next(it); cs1 = next(it)
        msg = next(it) if has_msg else None
        pos = None if sliding else next(it)
        dtype = h.dtype
        nr = L.unweighted_rms_norm(h.astype(mx.float32))
        ai = self.attention_input(bs, nr) if self.attention_input is not None else None
        if sliding:
            hs = ai[..., 0, :] if ai is not None else h
            if msg is None:
                qi = ki = vi = self.input_layernorm(hs).astype(dtype)
            else:
                st = self._mix_messages((hs,) * 3, msg)
                qi, ki, vi = [self.input_layernorm(s).astype(dtype) for s in st]
        else:
            q, k, v = (ai[..., i, :] for i in range(3))
            if msg is not None:
                q, k, v = self._mix_messages((q, k, v), msg)
            qi = self.q_input_layernorm(q).astype(dtype)
            ki = self.k_input_layernorm(k).astype(dtype)
            vi = self.v_input_layernorm(v).astype(dtype)
        qp, kp, vp, rp, gate, sinks = _proj(self, attn, qi, ki, vi, sliding and msg is None)
        if sliding:
            ks, w0 = attn.k_sconv(kp, cs0, None); vs, w1 = attn.v_sconv(vp, cs1, None)
        else:
            ks, w0 = attn.k_sconv(kp, ki, cs0, None); vs, w1 = attn.v_sconv(vp, vi, cs1, None)
        B, Ln = 1, 1
        qs = qp.reshape(B, Ln, attn.num_heads, -1)
        ks = ks.reshape(B, Ln, attn.num_key_value_heads, -1)
        vs = vs.reshape(B, Ln, attn.num_key_value_heads, -1)
        rs = rp.reshape(B, Ln, attn.num_heads, -1)
        qs = attn.q_l2_clip(qs); ks = attn.k_l2_clip(ks)
        vs = L.unweighted_rms_norm(vs.astype(mx.float32), attn.eps).astype(vs.dtype)
        rs = attn.rel_l2_clip(rs)
        if not sliding:
            tau = 1.0 + attn.log_scaling_alpha * mx.log(mx.maximum((pos + 1) / attn.log_scaling_n_floor, 1.0))
            tau = tau[..., None, None]
            qs = (qs.astype(mx.float32) * tau).astype(qs.dtype)
            rs = (rs.astype(mx.float32) * tau).astype(rs.dtype)
        pb = attn.rel_logits_proj(rs)
        return (qs.transpose(0, 2, 1, 3), ks.transpose(0, 2, 1, 3), vs.transpose(0, 2, 1, 3),
                pb, sinks, gate, nr, w0[:, 1:], w1[:, 1:])
    return mx.compile(body)


def _post(self, has_bs, has_msg):
    attn = self.self_attn

    def body(*args):
        it = iter(args)
        out = next(it); gate = next(it); h = next(it); nr = next(it)
        bs = next(it) if has_bs else None
        cs2 = next(it); cs3 = next(it)
        msg = next(it) if has_msg else None
        dtype = h.dtype
        ao = out.reshape(1, 1, -1).astype(mx.float32) * mx.sigmoid(gate.astype(mx.float32))
        hs = attn.o_proj(ao.astype(gate.dtype))
        hs, w2 = self.post_attention_convolution(hs, cs2, None)
        residual = hs = hs.astype(mx.float32)
        if self.is_block_boundary:
            block = nr[None]
            bs = block if bs is None else mx.concatenate([bs, block])
        else:
            residual = hs = h.astype(mx.float32) + hs
        ns = L.unweighted_rms_norm(hs)
        hs = self.mlp_input(bs, ns)[..., 0, :]
        if msg is not None:
            hs = self.mlp_message_gate(hs, msg[..., 3, :])
        hs = self.mlp(self.post_attention_layernorm(hs).astype(dtype))
        hs, w3 = self.post_mlp_convolution(hs, cs3, None)
        hs = residual + hs.astype(mx.float32)
        return hs.astype(dtype), bs, w2[:, 1:], w3[:, 1:]
    return mx.compile(body)


def _get(kind, self, has_bs, has_msg):
    key = (kind, id(self), has_bs, has_msg)
    f = _cache.get(key)
    if f is None:
        f = _cache[key] = (_pre if kind == "pre" else _post)(self, has_bs, has_msg)
    return f


# ---- mask kernel: mask[h, s] = visible ? (dist < R ? pb[h, dist] : 0) : -inf, same values as stock ----
_MASK_SRC = """
    uint s = thread_position_in_grid.x;
    uint h = thread_position_in_grid.y;
    int S = params[0]; int end = params[1]; int idx = params[2]; int rot = params[3];
    int window = params[4]; int R = params[5];
    if ((int)s >= S) return;
    int k = (int)s;
    if (rot) { k = ((k - idx) % S + S) % S; }
    int kpos = k + (end - S);
    int dist = (end - 1) - kpos;
    bool vis = (dist >= 0) && (kpos >= 0);
    if (window > 0) vis = vis && (dist < window);
    T v;
    if (!vis) v = T(-INFINITY);
    else if (dist < R) v = pb[h * R + dist];
    else v = T(0);
    out[h * S + s] = v;
"""
_mask_k = None


def _attention_fast(attn, q, keys, values, pb, sinks, kvc):
    global _mask_k
    if _mask_k is None:
        _mask_k = mx.fast.metal_kernel(name="ink_mask", input_names=["pb", "params"], output_names=["out"], source=_MASK_SRC)
    S = keys.shape[2]; end = kvc.offset; H = pb.shape[2]; R = pb.shape[-1]
    rot = isinstance(kvc, RotatingKVCache)
    params = mx.array([S, end, kvc._idx if rot else 0, int(rot), attn.sliding_window, R], mx.int32)
    mask = _mask_k(inputs=[pb[0, 0], params], template=[("T", q.dtype)], grid=(S, H, 1), threadgroup=(min(S, 256), 1, 1),
                   output_shapes=[(H, S)], output_dtypes=[q.dtype])[0]
    o = mx.fast.scaled_dot_product_attention(q, keys, values, scale=attn.scaling, mask=mask[None, :, None, :],
                                             sinks=sinks[0, 0].astype(q.dtype))
    return o.transpose(0, 2, 1, 3)


def call(self, hidden_states, block_states, *, cache=None, conv_mask=None, messages=None):
    conv = cache[1] if cache is not None else None
    if conv is None or hidden_states.shape[:2] != (1, 1) or conv.cache[0] is None or conv_mask is not None:
        return _orig(self, hidden_states, block_states, cache=cache, conv_mask=conv_mask, messages=messages)
    kvc = cache[0]; attn = self.self_attn
    has_bs = block_states is not None; has_msg = messages is not None
    args = [hidden_states] + ([block_states] if has_bs else []) + [conv[0], conv[1]] + ([messages] if has_msg else [])
    if not _sliding(self):
        args.append(mx.array([kvc.offset], mx.float32))
    q, k, v, pb, sinks, gate, nr, c0, c1 = _get("pre", self, has_bs, has_msg)(*args)
    keys, values = kvc.update_and_fetch(k, v)
    if OPTS["mask_kernel"]:
        out = _attention_fast(attn, q, keys, values, pb, sinks, kvc)
    else:
        out = attn._attention(q, keys, values, pb, sinks, kvc)
    args = [out, gate, hidden_states, nr] + ([block_states] if has_bs else []) + [conv[2], conv[3]] + ([messages] if has_msg else [])
    hs, bs, c2, c3 = _get("post", self, has_bs, has_msg)(*args)
    conv[0], conv[1], conv[2], conv[3] = c0, c1, c2, c3
    return hs, bs


def _cat_q(ps):
    f = nn.QuantizedLinear.__new__(nn.QuantizedLinear); nn.Module.__init__(f)
    f.group_size, f.bits, f.mode = ps[0].group_size, ps[0].bits, getattr(ps[0], "mode", "affine")
    f.weight = mx.concatenate([p.weight for p in ps]); f.scales = mx.concatenate([p.scales for p in ps])
    f.biases = mx.concatenate([p.biases for p in ps])
    f.freeze(); mx.eval(f.parameters())
    sizes = [p.weight.shape[0] for p in ps]
    return f, [sum(sizes[:i + 1]) for i in range(len(ps) - 1)]


def _fuse(model):
    for layer in model.model.language_model.layers:
        a = layer.self_attn
        if id(a) in _fused: continue
        ps = [a.q_proj, a.r_proj, a.gate_proj, a.sink_proj]
        if not all(isinstance(p, nn.QuantizedLinear) for p in ps): continue
        d = _fused[id(a)] = {}
        d["qrgs"], d["qrgs_split"] = _cat_q(ps)
        d["all6"], d["all6_split"] = _cat_q([a.q_proj, a.k_proj, a.v_proj, a.r_proj, a.gate_proj, a.sink_proj])


# ---- message gate: forget/message projections share the input -> one matmul ----
_orig_msg = L.MessageGate.__call__
_msgw = {}


def _fuse_msg(model):
    for layer in model.model.language_model.layers:
        for n in ("q_message_gate", "k_message_gate", "v_message_gate", "mlp_message_gate"):
            g = getattr(layer, n, None)
            if g is None or id(g) in _msgw: continue
            assert not isinstance(g.forget_gate_proj, nn.QuantizedLinear)
            w = mx.concatenate([g.forget_gate_proj.weight, g.message_gate_proj.weight]); mx.eval(w)
            _msgw[id(g)] = w


def _msg_call(self, hidden_states, message):
    states = mx.concatenate([L.unweighted_rms_norm(hidden_states), L.unweighted_rms_norm(message)], axis=-1)
    states = self.down_proj(states.astype(self.down_proj.weight.dtype)).astype(mx.float32)
    w = _msgw.get(id(self))
    if w is None:
        return _orig_msg(self, hidden_states, message)
    fm = mx.tanh(states @ w.T)
    forget_gate, message_gate = mx.split(fm, 2, axis=-1)
    return (1 - forget_gate) * hidden_states + message_gate * message


# ---- short conv as elementwise multiply-add for L=1 ----
_orig_conv = L.ShortConvolution.__call__


def _conv_call(self, hidden_states, conv_state, conv_mask):
    if hidden_states.shape[1] != 1 or conv_state is None or conv_mask is not None:
        return _orig_conv(self, hidden_states, conv_state, conv_mask)
    K = self.kernel_size
    residual = hidden_states.astype(mx.float32)
    window = L._conv_input(hidden_states, conv_state, conv_mask, K)
    w = self.conv1d.weight  # (C, K, 1)
    x = window.astype(w.dtype)
    out = (x.astype(mx.float32) * w[:, :, 0].T[None].astype(mx.float32)).sum(axis=1, keepdims=True).astype(w.dtype)
    out = (out.astype(mx.float32) + residual) / (K + 1) ** 0.5
    return out.astype(hidden_states.dtype), window


def apply(model, **opts):
    OPTS.update(_DEF); OPTS.update(opts); _cache.clear()
    if OPTS["fuse_proj"]: _fuse(model)
    L.DecoderLayer.__call__ = call
    if OPTS["fuse_msg"]: _fuse_msg(model); L.MessageGate.__call__ = _msg_call
    if OPTS["conv_ew"]: L.ShortConvolution.__call__ = _conv_call
    return {}


def revert(model):
    L.DecoderLayer.__call__ = _orig; _cache.clear()
    L.MessageGate.__call__ = _orig_msg; L.ShortConvolution.__call__ = _orig_conv

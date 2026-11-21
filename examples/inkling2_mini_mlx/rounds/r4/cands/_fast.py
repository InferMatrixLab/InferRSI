# 第 3 轮共用：解码一步（B=1, L=1）的每层走「前段合图 → 写缓存+注意力 → 后段合图」三段。
# 前段：残差取输入、消息门、归一化、q/k/v/r/门/汇点投影、短卷积、裁剪、相对位置偏置，一张编译图；
# 中段：KV 缓存写入和注意力（长度每步变，不编译）；
# 后段：门控、输出投影、卷积、残差、MoE、卷积，一张编译图。卷积状态当作显式输入输出。
# 选项：mask_kernel 把注意力遮罩的十几个小算子换成一个 Metal 内核；fuse_proj 把共享输入的投影拼成一次量化矩阵乘。
import mlx.core as mx
from mlx import nn
from mlx_lm.models.inkling2 import layers as L
from mlx_lm.models.cache import RotatingKVCache

OPTS = dict(mask_kernel=False, fuse_proj=False, fuse_all6=False, fuse_msg=False, conv_ew=False, conv_kernel=False, batch_msg=False)
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
            if same_kv and OPTS["fuse_all6"]:  # 滑窗层无消息：q/k/v 同一输入，六个投影一次
                qp, kp, vp, rp, gate, sinks = mx.split(f["all6"](qi), f["all6_split"], axis=-1)
                return qp, kp, vp, rp, gate, sinks
            kp = attn.k_proj(ki); vp = attn.v_proj(vi)
            return qp, kp, vp, rp, gate, sinks
    return attn.q_proj(qi), attn.k_proj(ki), attn.v_proj(vi), attn.r_proj(qi), attn.gate_proj(qi), attn.sink_proj(qi)


# ---- 短卷积内核（第 4 轮）：拼窗口、转权重精度、4 抽头深度卷积、加残差、除 sqrt(K+1)、出新状态，一个内核 ----
_CONV_SRC = """
    uint c = thread_position_in_grid.x;
    if (c >= (uint)C) return;
    float xs[4];
    for (int k = 0; k < 3; ++k) xs[k] = state[k * C + c];
    float xr = static_cast<float>(x[c]);
    xs[3] = xr;
    float acc = 0.0f;
    for (int k = 0; k < 4; ++k) acc += static_cast<float>(static_cast<WT>(xs[k])) * static_cast<float>(w[c * 4 + k]);
    WT o = static_cast<WT>(acc);
    float r = (static_cast<float>(o) + xr) / 2.2360679774997896f;
    out[c] = static_cast<OT>(r);
    for (int k = 0; k < 3; ++k) new_state[k * C + c] = xs[k + 1];
"""
_conv_k = None


def _sconv(conv, x, st):
    """返回 (输出, 新卷积状态)。"""
    global _conv_k
    if OPTS["conv_kernel"] and conv.kernel_size == 4:
        if _conv_k is None:
            _conv_k = mx.fast.metal_kernel(name="ink_sconv", input_names=["x", "state", "w"],
                                           output_names=["out", "new_state"], source=_CONV_SRC)
        C = x.shape[-1]; w = conv.conv1d.weight
        o, ns = _conv_k(inputs=[x, st, w], template=[("C", C), ("WT", w.dtype), ("OT", x.dtype)], grid=(C, 1, 1),
                        threadgroup=(256, 1, 1), output_shapes=[x.shape, st.shape], output_dtypes=[x.dtype, mx.float32])
        return o, ns
    o, win = conv(x, st, None)
    return o, win[:, 1:]


# ---- q/k/v 三个消息门批成一次批量矩阵乘（第 4 轮）----
_bw = {}


def _mix(self, states, msg):
    if not OPTS["batch_msg"]:
        return self._mix_messages(states, msg)
    gs = (self.q_message_gate, self.k_message_gate, self.v_message_gate)
    w = _bw.get(id(self))
    if w is None:
        wd = mx.stack([g.down_proj.weight for g in gs])  # (3, r, 2D)
        wf = mx.stack([mx.concatenate([g.forget_gate_proj.weight, g.message_gate_proj.weight]) for g in gs])  # (3, 2D, r)
        mx.eval(wd, wf); w = _bw[id(self)] = (wd, wf)
    wd, wf = w
    h = mx.stack(list(states))  # (3, B, L, D)
    m = mx.stack([msg[..., i, :] for i in range(3)])
    x = mx.concatenate([L.unweighted_rms_norm(h), L.unweighted_rms_norm(m)], axis=-1)
    x = x.astype(wd.dtype).reshape(3, -1, x.shape[-1])
    st = (x @ wd.swapaxes(-1, -2)).astype(mx.float32)
    fm = mx.tanh(st @ wf.swapaxes(-1, -2)).reshape(*h.shape[:-1], -1)
    fg, mg = mx.split(fm, 2, axis=-1)
    out = (1 - fg) * h + mg * m
    return out[0], out[1], out[2]


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
                st = _mix(self, (hs,) * 3, msg)
                qi, ki, vi = [self.input_layernorm(s).astype(dtype) for s in st]
        else:
            q, k, v = (ai[..., i, :] for i in range(3))
            if msg is not None:
                q, k, v = _mix(self, (q, k, v), msg)
            qi = self.q_input_layernorm(q).astype(dtype)
            ki = self.k_input_layernorm(k).astype(dtype)
            vi = self.v_input_layernorm(v).astype(dtype)
        qp, kp, vp, rp, gate, sinks = _proj(self, attn, qi, ki, vi, sliding and msg is None)
        if sliding:
            ks, n0 = _sconv(attn.k_sconv, kp, cs0); vs, n1 = _sconv(attn.v_sconv, vp, cs1)
        else:
            ks, w0 = attn.k_sconv(kp, ki, cs0, None); vs, w1 = attn.v_sconv(vp, vi, cs1, None)
            n0, n1 = w0[:, 1:], w1[:, 1:]
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
                pb, sinks, gate, nr, n0, n1)
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
        hs, n2 = _sconv(self.post_attention_convolution, hs, cs2)
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
        hs, n3 = _sconv(self.post_mlp_convolution, hs, cs3)
        hs = residual + hs.astype(mx.float32)
        return hs.astype(dtype), bs, n2, n3
    return mx.compile(body)


def _get(kind, self, has_bs, has_msg):
    key = (kind, id(self), has_bs, has_msg)
    f = _cache.get(key)
    if f is None:
        f = _cache[key] = (_pre if kind == "pre" else _post)(self, has_bs, has_msg)
    return f


# ---- 遮罩内核：mask[h, s] = 可见 ? (距离<R ? pb[h, 距离] : 0) : -inf，与原版逐元素同值 ----
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


# ---- 消息门：遗忘门和消息门两个投影共享输入，拼成一次矩阵乘 ----
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


# ---- 短卷积：深度卷积核 4 抽头，L=1 时写成逐元素乘加，免掉通用卷积内核 ----
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

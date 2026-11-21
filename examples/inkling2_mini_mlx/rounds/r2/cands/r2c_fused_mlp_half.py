"""Fuse the second half of every layer (depth residual for the MLP input -> message gate -> RMSNorm -> MoE)
into one compiled graph per layer instance. The attention half and the convolution state (cache writes) are untouched."""
import mlx.core as mx
from mlx_lm.models.inkling2 import layers as L
_orig = L.DecoderLayer.__call__
_cache = {}

def _half(self, has_msg):
    key = (id(self), has_msg)
    f = _cache.get(key)
    if f is None:
        def body(hidden_states, block_states, *msg):
            dtype = self._dtype
            normed = L.unweighted_rms_norm(hidden_states)
            h = self.mlp_input(block_states, normed)[..., 0, :]
            if msg:
                h = self.mlp_message_gate(h, msg[0][..., 3, :])
            return self.mlp(self.post_attention_layernorm(h).astype(dtype))
        f = _cache[key] = mx.compile(body)
    return f

def call(self, hidden_states, block_states, *, cache=None, conv_mask=None, messages=None):
    dtype = hidden_states.dtype
    self._dtype = dtype
    conv = cache[1] if cache is not None else None
    conv_states = list(conv.cache) if conv is not None else [None] * 4
    block_residual = hidden_states
    normed_residual = L.unweighted_rms_norm(block_residual.astype(mx.float32))
    attention_inputs = None
    if self.attention_input is not None:
        attention_inputs = self.attention_input(block_states, normed_residual)
    hidden_states = self._self_attention(hidden_states, attention_inputs, cache, conv_states, conv_mask, messages)
    hidden_states, conv_states[2] = self.post_attention_convolution(hidden_states, conv_states[2], conv_mask)
    residual = hidden_states = hidden_states.astype(mx.float32)
    if self.is_block_boundary:
        block = normed_residual[None]
        block_states = block if block_states is None else mx.concatenate([block_states, block])
    else:
        residual = hidden_states = block_residual.astype(mx.float32) + hidden_states
    if messages is not None:
        hidden_states = _half(self, True)(hidden_states, block_states, messages)
    else:
        hidden_states = _half(self, False)(hidden_states, block_states)
    hidden_states, conv_states[3] = self.post_mlp_convolution(hidden_states, conv_states[3], conv_mask)
    if conv is not None:
        n = self.post_mlp_convolution.kernel_size - 1
        for i, window in enumerate(conv_states):
            conv[i] = L._conv_state(window, conv.lengths, n)
        conv.advance(block_residual.shape[1])
    hidden_states = residual + hidden_states.astype(mx.float32)
    return hidden_states.astype(dtype), block_states

def apply(model):
    L.DecoderLayer.__call__ = call; return {}
def revert(model):
    L.DecoderLayer.__call__ = _orig

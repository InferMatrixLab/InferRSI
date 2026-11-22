"""Compile the depth-attention residual (BlockAttentionResidual, twice per layer)."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _patch
from mlx_lm.models.inkling2 import layers as L
def apply(model): _patch.compile_class(L.BlockAttentionResidual); return {}
def revert(model): _patch.revert_all()

"""r2c plus compiled q/k/v message gates in the attention half."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _patch
import r2c_fused_mlp_half as H
from mlx_lm.models.inkling2 import layers as L
def apply(model): H.apply(model); _patch.compile_class(L.MessageGate); return {}
def revert(model): H.revert(model); _patch.revert_all()

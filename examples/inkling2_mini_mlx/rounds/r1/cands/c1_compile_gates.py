"""Compile each loop message gate (MessageGate: two rms_norms, concat, three projections, two tanh) into one graph. Passes 2 and 3 of the loop call 4 gates per layer: about 96 calls per token."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _patch
from mlx_lm.models.inkling2 import layers as L
def apply(model): _patch.compile_class(L.MessageGate); return {}
def revert(model): _patch.revert_all()

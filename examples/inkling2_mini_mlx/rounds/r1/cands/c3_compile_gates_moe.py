"""c1 + c2 together."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _patch
from mlx_lm.models.inkling2 import layers as L
def apply(model): _patch.compile_class(L.MessageGate); _patch.compile_class(L.SparseMoeBlock); return {}
def revert(model): _patch.revert_all()

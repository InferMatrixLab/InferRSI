"""Round 3 e_msg: three-part layer decode path (pre graph / cache + attention / post graph), options [mask_kernel=True, fuse_proj=True, fuse_all6=True, fuse_msg=True]."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _fast
def apply(model): return _fast.apply(model, mask_kernel=True, fuse_proj=True, fuse_all6=True, fuse_msg=True)
def revert(model): _fast.revert(model)

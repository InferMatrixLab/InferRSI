"""Round 4 c_conv_batchmsg: round-3 three-part decode path, options [mask_kernel=True, fuse_proj=True, fuse_all6=True, fuse_msg=True, conv_kernel=True, batch_msg=True]."""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _fast
def apply(model): return _fast.apply(model, mask_kernel=True, fuse_proj=True, fuse_all6=True, fuse_msg=True, conv_kernel=True, batch_msg=True)
def revert(model): _fast.revert(model)

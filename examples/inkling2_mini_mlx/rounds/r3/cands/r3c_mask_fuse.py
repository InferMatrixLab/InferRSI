"""第 3 轮 c_mask_fuse：每层解码拆三段（前段合图/缓存+注意力/后段合图），选项 [mask_kernel=True, fuse_proj=True]。"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _fast
def apply(model): return _fast.apply(model, mask_kernel=True, fuse_proj=True)
def revert(model): _fast.revert(model)

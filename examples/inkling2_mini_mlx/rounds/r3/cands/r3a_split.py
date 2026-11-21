"""第 3 轮 a_split：每层解码拆三段（前段合图/缓存+注意力/后段合图），选项 []。"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); import _fast
def apply(model): return _fast.apply(model, )
def revert(model): _fast.revert(model)

"""Compatibility imports for the old run evaluator, composed in apps.legacy."""

from .apps.legacy.evaluation import _summary, evaluate, read_metric

__all__ = ["evaluate", "read_metric", "_summary"]

"""Shared engineering task contracts; execution belongs to the existing harness."""

from .contract import TaskPackage, builtin_tasks, load_builtin_task, load_task

__all__ = ["TaskPackage", "builtin_tasks", "load_builtin_task", "load_task"]

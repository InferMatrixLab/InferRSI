"""Load a task's own testable Python module from installed package resources."""

import importlib.util

from inferrsi.benchmark.registry import task_resources


def load_task_module(package, filename):
    path = task_resources(package).joinpath(filename + ".py")
    name = package.replace("-", "_") + "_" + filename
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

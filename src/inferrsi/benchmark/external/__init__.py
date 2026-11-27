"""Adapters for public benchmark suites whose tasks and graders live outside InferRSI.

A suite adapter reads one task package, names the reference controls the suite
ships, and judges the suite grader's own output. Executing a task (containers,
rootless staging, agents) belongs to Apps; see
``inferrsi.apps.workflows.external_benchmark``.
"""

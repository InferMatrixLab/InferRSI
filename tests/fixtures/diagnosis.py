"""Synthetic bottleneck evidence for optimization workflow tests."""


def diagnosis_evidence(root):
    summary = root.with_name(root.name + "-measurement.txt")
    summary.write_text("Synthetic workload: reference operation took 4 ms.", encoding="utf-8")
    return summary


def diagnosis_args(root, *command):
    return [*command, "diagnose", "--session", str(root),
            "--bottleneck", "Reference operation", "--evidence", str(diagnosis_evidence(root))]

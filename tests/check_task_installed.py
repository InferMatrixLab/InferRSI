"""Exercise the public task commands against an installed wheel without extras."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def command(*args, cwd):
    return subprocess.check_output(
        [sys.executable, "-I", "-m", "inferrsi", "task", *args],
        cwd=cwd,
        encoding="utf-8",
    )


fixture = Path(__file__).with_name("task-v1.yaml")
with TemporaryDirectory() as directory:
    root = Path(directory).resolve()
    path = root / fixture.name
    path.write_bytes(fixture.read_bytes())
    assert json.loads(command("schema", cwd=root))["schema_version"] == 1
    template = root / "template.yaml"
    template.write_text(command("template", cwd=root), encoding="utf-8")
    assert json.loads(command("validate", template.name, "--json", cwd=root)) == {"valid": True}
    assert json.loads(command("validate", path.name, "--json", cwd=root)) == {"valid": True}
    preview = json.loads(command("preview", path.name, "--json", cwd=root))
    assert preview["complete"] and preview["missing"] == []
    assert preview["task"]["optimization"]["repository"] == str(root / "checkout")
    assert preview["task"]["environment"]["backend"] == "cuda"
    assert preview["task"]["environment"]["repetitions"] == 2
    assert preview["task"]["environment"]["max_minutes"] == 1.5
    assert preview["task"]["acceptance"]["min_improvement_pct"] == 7.5
    assert set(root.iterdir()) == {path, template}
    assert path.read_bytes() == fixture.read_bytes()

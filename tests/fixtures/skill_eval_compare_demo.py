import argparse
import tempfile
from pathlib import Path

from tests.fixtures.skill_eval_compare_support import FixedOutputClient, configuration
from tools.skill_eval_compare import execute, prepare


def main():
    parser = argparse.ArgumentParser(description="Offline fixed-output comparison control")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("addition", "update"), default="update")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="se-demo-") as directory:
        root = Path(directory)
        config, repo = configuration(root, args.mode, ids=("fix", "regression", "error", "missing"),
                                     token_stop_new_trials=120)
        digest = prepare(config, repo, args.output.resolve())
        client = FixedOutputClient(root, {("fix", "baseline"): "incorrect",
            ("regression", "candidate"): "incorrect", ("error", "candidate"): "invalid_json"})
        result = execute(args.output.resolve(), digest, client=client)
        print(result["counts"])


if __name__ == "__main__":
    main()

import argparse
import tempfile
from pathlib import Path

from tests.fixtures.skill_eval_compare_support import FixedOutputClient
from tests.fixtures.skill_eval_pr_support import SimulatedGitHub, approval, setup
from tools import skill_eval_pr as integration


def main():
    parser = argparse.ArgumentParser(description="Offline PR integration with fixed outputs")
    parser.add_argument("--mode", choices=("addition", "update"), default="update")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="se-pr-demo-") as temporary:
        root = Path(temporary)
        repo, mapping, identity = setup(root, args.mode, token_stop_new_trials=200)
        plan = integration.prepare(repo, mapping, identity, output / "execution")
        client = FixedOutputClient(root, {("fix", "baseline"): "incorrect",
            ("regression", "candidate"): "incorrect", ("wrong", "baseline"): "incorrect",
            ("wrong", "candidate"): "incorrect", ("error", "candidate"): "invalid_json"})
        integration.execute(output / "execution", approval(plan), client=client)
        data = integration.result_archive(output / "execution").read_bytes()
        integration.prepare(repo, mapping, identity, output / "publication")
        api = SimulatedGitHub(plan, data)
        integration.publish_retained(api, output / "publication", 10, 11, 1)
        (output / "pr-summary.md").write_text(api.comments[0]["body"], encoding="utf-8")
        print({"mode": args.mode, "fixed_output_calls": len(client.calls),
               "pr_plan_sha256": integration.fingerprint(plan), "simulated_comments": 1})


if __name__ == "__main__":
    main()

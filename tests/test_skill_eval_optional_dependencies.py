"""Lightweight controllers must remain usable without the optional skills parser."""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class OptionalSkillsDependencyTests(unittest.TestCase):
    def run_without_yaml(self, source):
        root = Path(__file__).resolve().parents[1]
        script = (
            f"import sys; sys.path[:0] = {[str(root), str(root / 'src')]!r}\n"
            "sys.modules['yaml'] = None\n"
            + textwrap.dedent(source)
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", script],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_comparison_reporting_without_yaml(self):
        self.run_without_yaml("""
            from tools.skill_eval_compare import condition_summary, read_report

            summary = condition_summary([])
            assert set(summary) == {'baseline', 'candidate'}
            assert all(item['input_tokens'] is None for item in summary.values())
            assert callable(read_report)
            assert 'inferrsi.skill_catalog' not in sys.modules
        """)

    def test_checkpoint_without_yaml(self):
        self.run_without_yaml("""
            from tools.goal_checkpoint import recommend

            result = recommend({'problems': ['missing_evidence'], 'sources': {},
                                'input_sha256': '0' * 64})
            assert result.action == 'repair_evidence'
            assert result.reasons == ('missing_evidence',)
            assert 'inferrsi.skill_catalog' not in sys.modules
        """)

    def test_daily_controller_without_yaml(self):
        self.run_without_yaml("""
            from tools.skill_eval_auto import daily_anchor
            from tools.skill_eval_budget import BudgetError

            try:
                daily_anchor({'schema_version': 1})
            except BudgetError as error:
                assert 'Audited global daily genesis' in str(error)
            else:
                raise AssertionError('Daily controller accepted missing budget configuration')
            assert 'inferrsi.skill_catalog' not in sys.modules
        """)

    def test_selected_snapshot_still_requires_yaml_before_side_effects(self):
        self.run_without_yaml("""
            import tempfile
            from pathlib import Path
            from unittest.mock import patch
            from tools.skill_eval_snapshot import selected_snapshot

            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                destination = root / 'output'
                with patch('subprocess.check_output') as git:
                    try:
                        selected_snapshot(root, 'a' * 40, 'library', 'selected', destination)
                    except ValueError as error:
                        assert "'skills' extra (PyYAML)" in str(error), str(error)
                    else:
                        raise AssertionError('Selected snapshot silently skipped the skills parser')
                    git.assert_not_called()
                assert not destination.exists()
        """)


if __name__ == "__main__":
    unittest.main()

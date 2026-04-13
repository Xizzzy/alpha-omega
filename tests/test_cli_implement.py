import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from alpha_omega import cli
from alpha_omega.primitives import BrainResult


def _write_session(project_dir, session_id, winning_brain):
    sessions_dir = os.path.join(project_dir, ".alpha-omega", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    session_file = os.path.join(sessions_dir, "%s.json" % session_id)
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "session_id": session_id,
                "resolution": "ADOPT_WITH_DISSENT",
                "winning_option": "winner when unique",
                "winning_brain": winning_brain,
                "implementable": True,
                "implementation_brief": {
                    "goal": "Quick test: should ao implement default to the winner brain? Answer briefly.",
                    "winning_option": "winner when unique",
                    "winning_thesis": "Default to the unique winner; require --executor on ties.",
                    "constraints": [],
                    "dissent": "",
                    "open_questions": [],
                },
                "attempts": [],
            },
            f,
            indent=2,
        )
    return session_file


class ImplementExecutorTests(unittest.TestCase):
    def test_resolve_executor_allows_unique_winner(self):
        executor = cli._resolve_implement_executor(
            {"winning_brain": "omega"},
            "winner",
            "ao_123",
        )
        self.assertEqual(executor, "omega")

    def test_cmd_implement_requires_explicit_executor_for_ambiguous_winner(self):
        with tempfile.TemporaryDirectory() as project_dir:
            session_id = "ao_ambiguous"
            _write_session(project_dir, session_id, "both")
            args = Namespace(
                project=project_dir,
                session_id=session_id,
                executor="winner",
                model=None,
                timeout=1,
                force=False,
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("alpha_omega.primitives.run_alpha") as run_alpha:
                with mock.patch("alpha_omega.primitives.run_omega") as run_omega:
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.cmd_implement(args)

            self.assertEqual(exit_code, 1)
            self.assertIn("ambiguous winning_brain='both'", stderr.getvalue())
            self.assertIn("--executor alpha or --executor omega", stderr.getvalue())
            self.assertFalse(run_alpha.called)
            self.assertFalse(run_omega.called)
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        project_dir,
                        ".alpha-omega",
                        "sessions",
                        "%s.lock.json" % session_id,
                    )
                )
            )

    def test_cmd_implement_defaults_to_unique_winner_brain(self):
        with tempfile.TemporaryDirectory() as project_dir:
            session_id = "ao_unique"
            session_file = _write_session(project_dir, session_id, "omega")
            args = Namespace(
                project=project_dir,
                session_id=session_id,
                executor="winner",
                model=None,
                timeout=1,
                force=False,
            )

            result = BrainResult(brain="Omega", phase="implement")
            result.text = json.dumps(
                {
                    "status": "completed",
                    "summary": "Implemented the winning executor selection.",
                    "files_changed": ["alpha_omega/cli.py"],
                    "commands_ran": ["python -m unittest tests.test_cli_implement"],
                    "checks": ["tests pass"],
                    "blockers": [],
                    "next_steps": [],
                }
            )
            result.duration = 0.2

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("alpha_omega.primitives.run_omega", return_value=result) as run_omega:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.cmd_implement(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            run_omega.assert_called_once()
            self.assertIn("Executor: OMEGA (Codex)", stdout.getvalue())

            with open(session_file, encoding="utf-8") as f:
                session = json.load(f)
            self.assertEqual(session["attempts"][0]["executor"], "omega")
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        project_dir,
                        ".alpha-omega",
                        "sessions",
                        "%s.lock.json" % session_id,
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()

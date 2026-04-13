#!/usr/bin/env python3
"""cli.py — Alpha-Omega CLI entry point.

Usage:
    ao debate "question"                  # Run a full debate session
    ao debate --file prompt.txt           # Question from file
    ao debate --mode specify "question"   # Specify mode (explore|specify|build|audit)
    ao debate --extra bot/config.py "q"   # Include extra files in context
    ao doctor                             # Check prerequisites before first use
    ao init                               # Bootstrap .alpha-omega/ in current project
    ao history                            # Show recent debate decisions
    ao status                             # Show current project AO state

Python 3.9 compatible.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys

from .protocol import DebateSession
from .artifacts import save_to_project

__version__ = "0.2.0"


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_doctor(args):
    """Check prerequisites: CLIs, auth, Python, project state."""
    project_dir = args.project or os.getcwd()
    ok = True
    warnings = []

    def check(label, passed, fix=""):
        nonlocal ok
        status = "ok" if passed else "FAIL"
        print("  [%s] %s" % (status, label))
        if not passed:
            ok = False
            if fix:
                print("        fix: %s" % fix)

    print("Alpha-Omega Doctor")
    print("=" * 40)
    print()

    # Python version
    py_ver = sys.version_info
    check(
        "Python %d.%d.%d (need 3.9+)" % (py_ver.major, py_ver.minor, py_ver.micro),
        py_ver >= (3, 9),
        fix="Install Python 3.9 or newer",
    )

    # Claude CLI
    claude_path = shutil.which("claude")
    check(
        "Claude CLI" + (" (%s)" % claude_path if claude_path else ""),
        claude_path is not None,
        fix="Install: https://docs.anthropic.com/en/docs/claude-code",
    )

    # Claude auth
    if claude_path:
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            claude_version = result.stdout.strip() or result.stderr.strip()
            check("Claude version: %s" % claude_version[:60], True)
        except Exception:
            check("Claude version check", False, fix="Run: claude --version")

    # Codex CLI
    codex_path = shutil.which("codex")
    check(
        "Codex CLI" + (" (%s)" % codex_path if codex_path else ""),
        codex_path is not None,
        fix="Install: npm install -g @openai/codex",
    )

    # Codex auth
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    codex_auth = os.path.expanduser("~/.codex/auth.json")
    has_codex_auth = bool(openai_key) or os.path.isfile(codex_auth)
    if codex_path:
        check(
            "Codex auth" + (" (env)" if openai_key else " (~/.codex/auth.json)" if os.path.isfile(codex_auth) else ""),
            has_codex_auth,
            fix="Run: codex auth login  OR  set OPENAI_API_KEY",
        )

    # Project state
    print()
    print("Project: %s" % project_dir)
    print("-" * 40)

    ao_dir = os.path.join(project_dir, ".alpha-omega")
    check(
        ".alpha-omega/ initialized",
        os.path.isdir(ao_dir),
        fix="Run: ao init",
    )

    agents_path = os.path.join(project_dir, "AGENTS.md")
    check(
        "AGENTS.md (Omega memory)",
        os.path.isfile(agents_path),
        fix="Run: ao init  (creates AGENTS.md if missing)",
    )

    claude_md = os.path.join(project_dir, "CLAUDE.md")
    has_claude_md = os.path.isfile(claude_md)
    check(
        "CLAUDE.md (Alpha memory)",
        has_claude_md,
        fix="Create CLAUDE.md with project description for Alpha",
    )

    # Write access
    test_file = os.path.join(project_dir, ".ao_write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        can_write = True
    except OSError:
        can_write = False
    check("Write access to project dir", can_write)

    print()
    if ok:
        print("All checks passed. Ready to debate!")
        print()
        if not os.path.isdir(ao_dir):
            print("Next step: ao init")
        else:
            print('Next step: ao debate "your question"')
    else:
        print("Some checks failed. Fix the issues above and run ao doctor again.")

    return 0 if ok else 1


def cmd_debate(args):
    """Run a full Alpha-Omega debate session."""
    # Get the question
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            question = f.read().strip()
    elif args.question:
        question = " ".join(args.question)
    else:
        print("Error: provide a question or --file", file=sys.stderr)
        return 1

    if not question:
        print("Error: empty question", file=sys.stderr)
        return 1

    extra_files = args.extra or []
    project_dir = args.project or os.getcwd()

    print("=" * 60)
    print("Alpha-Omega Debate Session")
    print("=" * 60)
    print("Question: %s" % question[:200])
    print("Mode: %s" % args.mode)
    print("Project: %s" % project_dir)
    print("=" * 60)
    print()

    session = DebateSession(
        question=question,
        project_dir=project_dir,
        extra_files=extra_files,
        mode=args.mode,
        model=getattr(args, "model", None),
        timeout=getattr(args, "timeout", None),
    )

    result = session.run()

    if "error" in result:
        print("ERROR: %s" % result["error"], file=sys.stderr)
        return 1

    # Print the artifact pack
    print(result.get("markdown", "No output generated"))

    # Save to project
    if not args.no_save:
        try:
            saved = save_to_project(result, project_dir)
            print("\n---")
            print("Debate saved to: %s" % saved)
        except Exception as exc:
            print("Warning: could not save to project: %s" % exc, file=sys.stderr)

    # Also save raw JSON for programmatic use
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result.get("decision", {}), f, indent=2, default=str)
        print("Decision JSON saved to: %s" % args.json_out)

    return 0


def cmd_init(args):
    """Bootstrap .alpha-omega/ in the current project."""
    project_dir = args.project or os.getcwd()
    ao_dir = os.path.join(project_dir, ".alpha-omega")
    debates_dir = os.path.join(ao_dir, "debates")

    if os.path.isdir(ao_dir):
        print(".alpha-omega/ already exists in %s" % project_dir)
        return 0

    os.makedirs(debates_dir, exist_ok=True)

    # INDEX.md
    index_content = """# Alpha-Omega Memory

This directory stores the project-local memory for Alpha-Omega debate sessions.

## Files

- `decisions.md` — log of all debate outcomes
- `debates/` — full debate transcripts (one file per session)

## Usage

Run `ao debate "your question"` from this project directory.
Both Alpha (Claude) and Omega (Codex) will read project context automatically.
"""
    with open(os.path.join(ao_dir, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write(index_content)

    # decisions.md
    with open(os.path.join(ao_dir, "decisions.md"), "w", encoding="utf-8") as f:
        f.write("# Alpha-Omega Decisions\n\nDecision log for this project.\n")

    # AGENTS.md (for Omega/Codex) — only if it doesn't exist
    agents_path = os.path.join(project_dir, "AGENTS.md")
    if not os.path.isfile(agents_path):
        agents_content = """# %s

> **You are Omega** (GPT/Codex), one half of the Alpha-Omega dual-brain system.
> Alpha (Claude) is the other half. You are NOT a consultant — you are a teammate
> with equal authority to propose, critique, and decide.

## Your mandate

1. **Debate, don't defer.** Push back on Alpha's reasoning with evidence.
2. **Edit freely.** You have write access. Fix what you see.
3. **Refuse nonsense.** "Interesting but nothing to do" is not valid unless true.

## Project context

Read `.alpha-omega/INDEX.md` and project docs before answering.
""" % os.path.basename(project_dir)
        with open(agents_path, "w", encoding="utf-8") as f:
            f.write(agents_content)
        print("Created AGENTS.md (Omega's memory)")

    print("Initialized .alpha-omega/ in %s" % project_dir)
    print("  %s" % os.path.join(ao_dir, "INDEX.md"))
    print("  %s" % os.path.join(ao_dir, "decisions.md"))
    print("  %s" % debates_dir)
    return 0


def cmd_history(args):
    """Show recent debate decisions."""
    project_dir = args.project or os.getcwd()
    decisions_file = os.path.join(project_dir, ".alpha-omega", "decisions.md")

    if not os.path.isfile(decisions_file):
        print("No decisions found. Run 'ao init' first.", file=sys.stderr)
        return 1

    with open(decisions_file, encoding="utf-8") as f:
        content = f.read()

    # Show last N entries
    entries = content.split("### ")
    n = args.last or 5
    if len(entries) > 1:
        recent = entries[-n:]
        for entry in recent:
            if entry.strip():
                print("### " + entry)
                print()
    else:
        print("No debate history yet.")

    return 0


def cmd_status(args):
    """Show AO status for current project."""
    project_dir = args.project or os.getcwd()
    ao_dir = os.path.join(project_dir, ".alpha-omega")

    print("Project: %s" % project_dir)
    print("AO initialized: %s" % ("yes" if os.path.isdir(ao_dir) else "no"))

    if os.path.isdir(ao_dir):
        decisions_file = os.path.join(ao_dir, "decisions.md")
        debates_dir = os.path.join(ao_dir, "debates")
        if os.path.isfile(decisions_file):
            with open(decisions_file) as f:
                count = f.read().count("### ao_")
            print("Total debates: %d" % count)
        if os.path.isdir(debates_dir):
            files = [f for f in os.listdir(debates_dir) if f.endswith(".md")]
            print("Debate transcripts: %d" % len(files))

    agents_path = os.path.join(project_dir, "AGENTS.md")
    print("AGENTS.md (Omega): %s" % ("present" if os.path.isfile(agents_path) else "missing"))
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    print("CLAUDE.md (Alpha): %s" % ("present" if os.path.isfile(claude_md) else "missing"))

    return 0


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="ao",
        description="Alpha-Omega: dual-brain thinking tool (v%s)" % __version__,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("-V", "--version", action="version", version="ao %s" % __version__)
    parser.add_argument("--project", help="Project directory (default: cwd)")

    sub = parser.add_subparsers(dest="command")

    # doctor
    sub.add_parser("doctor", help="Check prerequisites and project state")

    # debate
    p_debate = sub.add_parser("debate", help="Run a debate session")
    p_debate.add_argument("question", nargs="*", help="The question to debate")
    p_debate.add_argument("--file", help="Read question from file")
    p_debate.add_argument("--mode", default="explore",
                          choices=["explore", "specify", "build", "audit"],
                          help="Output mode")
    p_debate.add_argument("--extra", action="append",
                          help="Extra files to include in context (repeatable)")
    p_debate.add_argument("--no-save", action="store_true",
                          help="Don't save results to .alpha-omega/")
    p_debate.add_argument("--json-out", help="Save decision JSON to file")
    p_debate.add_argument("--model", default=None,
                          help="Alpha model (default: claude-sonnet-4-5)")
    p_debate.add_argument("--timeout", type=int, default=None,
                          help="Timeout per brain call in seconds (default: 300)")

    # init
    sub.add_parser("init", help="Bootstrap .alpha-omega/ in project")

    # history
    p_history = sub.add_parser("history", help="Show recent decisions")
    p_history.add_argument("--last", type=int, default=5, help="Number of entries")

    # status
    sub.add_parser("status", help="Show AO status for project")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "doctor":
        return cmd_doctor(args)
    elif args.command == "debate":
        return cmd_debate(args)
    elif args.command == "init":
        return cmd_init(args)
    elif args.command == "history":
        return cmd_history(args)
    elif args.command == "status":
        return cmd_status(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

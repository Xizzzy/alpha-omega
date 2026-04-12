#!/usr/bin/env python3
"""ao.py — Alpha-Omega CLI entry point.

Usage:
    ao debate "question"                  # Run a full debate session
    ao debate --file prompt.txt           # Question from file
    ao debate --mode specify "question"   # Specify mode (explore|specify|build|audit)
    ao debate --extra bot/config.py "q"   # Include extra files in context
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
import sys

# Ensure core/ is importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from core.protocol import DebateSession
from core.artifacts import save_to_project


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
        description="Alpha-Omega: dual-brain thinking tool",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--project", help="Project directory (default: cwd)")

    sub = parser.add_subparsers(dest="command")

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

    # init
    sub.add_parser("init", help="Bootstrap .alpha-omega/ in project")

    # history
    p_history = sub.add_parser("history", help="Show recent decisions")
    p_history.add_argument("--last", type=int, default=5, help="Number of entries")

    # status
    sub.add_parser("status", help="Show AO status for project")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "debate":
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

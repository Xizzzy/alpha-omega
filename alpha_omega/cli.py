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

__version__ = "0.3.2"


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


# ---------------------------------------------------------------------------
# Welcome & Setup
# ---------------------------------------------------------------------------

_SAMPLE_DEBATE = (
    'ao debate --mode audit '
    '"Audit this project: what are the top 3 risks, '
    'top 3 strengths, and the single highest-leverage improvement?"'
)


def _show_welcome(args):
    """Stateful welcome message instead of raw argparse help."""
    project_dir = args.project or os.getcwd()
    ao_dir = os.path.join(project_dir, ".alpha-omega")
    is_setup = os.path.isdir(ao_dir)

    print("Alpha-Omega v%s" % __version__)
    print("Two independent AI brains. One resolved answer.")
    print()

    if not is_setup:
        print("Get started:")
        print("  ao setup           Check prerequisites + initialize project")
        print()
        print("Or step by step:")
        print("  ao doctor          Check Claude + Codex CLIs")
        print("  ao init            Create .alpha-omega/ in this project")
        print("  %s" % _SAMPLE_DEBATE)
    else:
        print("Commands:")
        print("  ao debate \"...\"    Full dual-brain debate")
        print("  ao review          Quick code review (staged/unstaged/branch)")
        print("  ao implement ID    Execute a debate resolution")
        print("  ao recall QUERY    Search past decisions")
        print("  ao contradictions  Find conflicting past decisions")
        print("  ao history         Recent debate outcomes")
        print("  ao status          Project state")
        print("  ao doctor          Check prerequisites")

    print()
    print("Use ao --help for full options.")
    return 0


def cmd_setup(args):
    """First-time setup: doctor + init + first-run guidance."""
    project_dir = args.project or os.getcwd()

    print("Alpha-Omega Setup")
    print("=" * 40)
    print()

    # Step 1: Doctor checks (non-blocking)
    print("Step 1/3  Checking prerequisites")
    print("-" * 40)

    issues = []

    claude_path = shutil.which("claude")
    codex_path = shutil.which("codex")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    codex_auth = os.path.expanduser("~/.codex/auth.json")

    def check(label, passed, fix=""):
        status = "ok" if passed else "warn"
        print("  [%s] %s" % (status, label))
        if not passed and fix:
            print("        fix: %s" % fix)
            issues.append(fix)

    check("Python %d.%d" % (sys.version_info.major, sys.version_info.minor),
          sys.version_info >= (3, 9), fix="Install Python 3.9+")
    check("Claude CLI", claude_path is not None,
          fix="Install: https://docs.anthropic.com/en/docs/claude-code")
    if claude_path:
        has_claude_auth = _check_claude_auth()
        check("Claude auth", has_claude_auth,
              fix="Run: claude auth login")

    check("Codex CLI", codex_path is not None,
          fix="Install: npm install -g @openai/codex")
    if codex_path:
        check("Codex auth", bool(openai_key) or os.path.isfile(codex_auth),
              fix="Run: codex login")
    print()

    if issues:
        print("Some prerequisites missing (see fixes above).")
        print("You can still initialize — debates will work once CLIs are ready.")
        print()

    # Step 2: Init
    print("Step 2/3  Initializing project memory")
    print("-" * 40)

    # Delegate to cmd_init logic but inline for cleaner output
    ao_dir = os.path.join(project_dir, ".alpha-omega")
    debates_dir = os.path.join(ao_dir, "debates")

    if os.path.isdir(ao_dir):
        print("  [ok] .alpha-omega/ already exists")
    else:
        os.makedirs(debates_dir, exist_ok=True)
        with open(os.path.join(ao_dir, "INDEX.md"), "w", encoding="utf-8") as f:
            f.write("# Alpha-Omega Memory\n\nDecision memory for this project.\n"
                    "Run `ao debate \"question\"` or `ao review` to get started.\n")
        with open(os.path.join(ao_dir, "decisions.md"), "w", encoding="utf-8") as f:
            f.write("# Alpha-Omega Decisions\n\nDecision log for this project.\n")
        _write_ao_gitignore(ao_dir)
        print("  [created] .alpha-omega/")

    # AGENTS.md
    agents_path = os.path.join(project_dir, "AGENTS.md")
    if os.path.isfile(agents_path):
        print("  [ok] AGENTS.md already exists")
    else:
        project_name = os.path.basename(os.path.abspath(project_dir))
        with open(agents_path, "w", encoding="utf-8") as f:
            f.write("# %s\n\n" % project_name)
            f.write("> **You are Omega** (GPT/Codex), one half of the Alpha-Omega dual-brain system.\n")
            f.write("> Alpha (Claude) is the other half. You have equal authority to propose,\n")
            f.write("> critique, and decide.\n\n")
            f.write("## Your mandate\n\n")
            f.write("1. **Debate, don't defer.** Push back on Alpha with evidence.\n")
            f.write("2. **Edit freely.** You have write access.\n")
            f.write("3. **Refuse nonsense.** Be honest, not agreeable.\n\n")
            f.write("## Project context\n\nRead `.alpha-omega/INDEX.md` and CLAUDE.md before answering.\n")
        print("  [created] AGENTS.md")

    # CLAUDE.md
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if os.path.isfile(claude_md):
        print("  [ok] CLAUDE.md already exists")
    else:
        project_name = os.path.basename(os.path.abspath(project_dir))
        with open(claude_md, "w", encoding="utf-8") as f:
            f.write("# %s\n\n" % project_name)
            f.write("## What this project is\n\n")
            f.write("<!-- TODO: Describe what this project does -->\n\n")
            f.write("## Architecture\n\n")
            f.write("<!-- TODO: Key files, modules, how things connect -->\n\n")
            f.write("## Commands\n\n")
            f.write("<!-- TODO: How to build, test, run -->\n\n")
            f.write("## Constraints\n\n")
            f.write("<!-- TODO: Language version, dependencies, rules -->\n\n")
        print("  [created] CLAUDE.md (fill in the TODOs for better debate quality)")

    print()

    # Install global Claude Code skill
    # Config
    from .config import save_default_config
    config_file = os.path.join(ao_dir, "config.json")
    if os.path.isfile(config_file):
        print("  [ok] config.json already exists")
    else:
        if save_default_config(project_dir):
            print("  [created] config.json (alpha_model, timeouts)")

    # Claude Code skill
    skill_dir = os.path.expanduser("~/.claude/skills/alpha-omega")
    skill_file = os.path.join(skill_dir, "SKILL.md")
    if os.path.isfile(skill_file):
        print("  [ok] Claude Code skill already installed")
    else:
        try:
            os.makedirs(skill_dir, exist_ok=True)
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(_SKILL_CONTENT)
            print("  [created] Claude Code skill (~/.claude/skills/alpha-omega/)")
            print("           Use /alpha-omega from any Claude Code session")
        except OSError as exc:
            print("  [warn] Could not install skill: %s" % exc)

    print()

    # Step 3: First run guidance
    print("Step 3/3  Ready to go")
    print("-" * 40)
    print()
    print("Try your first debate:")
    print("  %s" % _SAMPLE_DEBATE)
    print()
    print("Or review your current changes:")
    print("  ao review")
    print()

    return 0


def _check_claude_auth():
    """Check Claude auth via 'claude auth status'. Returns True if logged in."""
    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        return data.get("loggedIn", False)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


_SKILL_CONTENT = """---
name: alpha-omega
description: "Run an Alpha-Omega dual-brain debate. Two different AI systems (Claude + Codex) independently analyze a problem, then debate to find blind spots."
---

# Alpha-Omega Dual-Brain Debate

Run `ao` commands to orchestrate debates between Claude (Alpha) and Codex (Omega).

## Commands

```bash
ao setup                         # First-time setup
ao debate "question"             # Full debate
ao review [--staged|--branch X]  # Quick code review
ao implement <id> --executor X   # Execute a resolution
ao recall <query>                # Search past decisions
ao contradictions                # Find conflicting decisions
ao doctor                        # Check prerequisites
ao history                       # Recent outcomes
```

## When to use

- Architecture decisions before implementation
- Non-trivial trade-off decisions
- Code review before merge
- Strategy debates

## Modes

- `--mode explore` (default): Options + recommendation
- `--mode specify`: Architecture + spec
- `--mode build`: Spec + tasks
- `--mode audit`: Critique existing design
"""


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

        has_claude_auth = _check_claude_auth()
        check("Claude auth", has_claude_auth,
              fix="Run: claude auth login")

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
    from .config import load_config

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
    config = load_config(project_dir)

    print("=" * 60)
    print("Alpha-Omega Debate Session")
    print("=" * 60)
    print("Question: %s" % question[:200])
    print("Mode: %s" % args.mode)
    print("Project: %s" % project_dir)
    print("=" * 60)
    print()

    # Precedence: specific flag > shared --timeout > config value.
    shared_timeout = getattr(args, "timeout", None)
    alpha_timeout = getattr(args, "alpha_timeout", None) or shared_timeout or config["alpha_timeout"]
    omega_timeout = getattr(args, "omega_timeout", None) or shared_timeout or config["omega_timeout"]
    alpha_max_turns = getattr(args, "alpha_max_turns", None) or config["alpha_max_turns"]

    session = DebateSession(
        question=question,
        project_dir=project_dir,
        extra_files=extra_files,
        mode=args.mode,
        model=getattr(args, "model", None) or config["alpha_model"],
        alpha_timeout=alpha_timeout,
        omega_timeout=omega_timeout,
        alpha_max_turns=alpha_max_turns,
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


def cmd_review(args):
    """Run a lightweight dual-brain code review."""
    from .config import load_config
    from .context_builder import build_review_context
    from .review import ReviewSession

    project_dir = args.project or os.getcwd()
    config = load_config(project_dir)

    # Determine scope
    if args.branch:
        scope = "branch:%s" % args.branch
    elif args.staged:
        scope = "staged"
    else:
        scope = "unstaged"

    print("Alpha-Omega Review")
    print("=" * 40)
    print("Scope: %s" % scope)
    print("Project: %s" % project_dir)
    print()

    # Build review context
    review_ctx = build_review_context(project_dir, scope)

    if review_ctx.get("error"):
        print("Error: %s" % review_ctx["error"], file=sys.stderr)
        return 1

    if not review_ctx.get("diff", "").strip() and not review_ctx.get("new_files"):
        print("No changes to review.")
        return 0

    print("Files changed: %d" % len(review_ctx.get("files_changed", [])))
    for f_name in review_ctx.get("files_changed", [])[:10]:
        print("  %s" % f_name)
    if len(review_ctx.get("files_changed", [])) > 10:
        print("  ... and %d more" % (len(review_ctx["files_changed"]) - 10))
    print()

    # Run review
    session = ReviewSession(
        review_ctx,
        model=getattr(args, "model", None) or config["alpha_model"],
        timeout=getattr(args, "timeout", None) or config["review_timeout"],
    )
    result = session.run()

    if "error" in result:
        print("ERROR: %s" % result["error"], file=sys.stderr)
        return 1

    # Render output
    verdict = result.get("verdict", "?")
    verdict_icon = {"safe": "SAFE", "risky": "RISKY", "needs-debate": "NEEDS DEBATE"}.get(verdict, verdict.upper())

    print("=" * 40)
    print("Verdict: %s" % verdict_icon)
    print("Agreement: %s" % result.get("agreement", "?"))
    print("Duration: %.0fs" % result.get("duration_s", 0))
    print("=" * 40)
    print()

    # Alpha & Omega summaries
    if result.get("alpha_summary"):
        print("Alpha: %s" % result["alpha_summary"])
    if result.get("omega_summary"):
        print("Omega: %s" % result["omega_summary"])
    if result.get("alpha_summary") or result.get("omega_summary"):
        print()

    # Risks
    risks = result.get("risks", [])
    if risks:
        print("Risks (%d):" % len(risks))
        for risk in risks:
            sev = risk.get("severity", "?")
            desc = risk.get("description", "")
            f_name = risk.get("file", "")
            if f_name:
                print("  [%s] %s (%s)" % (sev, desc, f_name))
            else:
                print("  [%s] %s" % (sev, desc))
        print()

    # Missing tests
    tests = result.get("missing_tests", [])
    if tests:
        print("Missing tests:")
        for t in tests:
            print("  - %s" % t)
        print()

    # Dissent
    if result.get("dissent"):
        print("Dissent: %s" % result["dissent"])
        print()

    # Escalation
    if result.get("should_escalate"):
        print(">>> Auto-escalation recommended: %s" % result.get("escalation_reason", ""))
        print('>>> Run: ao debate "Review escalation: %s"' % " ".join(
            review_ctx.get("files_changed", [])[:3]))
        print()

    # Save if requested
    if args.save:
        ao_dir = os.path.join(project_dir, ".alpha-omega")
        reviews_dir = os.path.join(ao_dir, "reviews")
        os.makedirs(reviews_dir, exist_ok=True)
        review_file = os.path.join(reviews_dir, "%s.json" % result["session_id"])
        with open(review_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print("Review saved to: %s" % review_file)

    return 0


def _write_ao_gitignore(ao_dir):
    """Create .gitignore inside .alpha-omega/ to keep git clean."""
    gitignore_path = os.path.join(ao_dir, ".gitignore")
    if os.path.isfile(gitignore_path):
        return
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("# Keep decisions.md, config.json, INDEX.md in git\n")
        f.write("# Ignore generated debate/review artifacts\n")
        f.write("debates/\n")
        f.write("sessions/\n")
        f.write("reviews/\n")


def _validate_session_id(session_id):
    """Validate session_id to prevent path traversal."""
    import re
    if not re.match(r'^ao[r]?_\d+$', session_id):
        raise ValueError("Invalid session ID: %s (expected ao_<digits> or aor_<digits>)" % session_id)
    return session_id


def cmd_implement(args):
    """Run implementation based on a resolved debate session."""
    from .config import load_config
    from .primitives import run_alpha, run_omega, parse_json_response

    project_dir = args.project or os.getcwd()
    config = load_config(project_dir)
    executor = args.executor

    try:
        session_id = _validate_session_id(args.session_id)
    except ValueError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1

    # Load session JSON
    session_file = os.path.join(project_dir, ".alpha-omega", "sessions", "%s.json" % session_id)
    if not os.path.isfile(session_file):
        print("Error: session file not found: %s" % session_file, file=sys.stderr)
        print("Run 'ao history' to see available sessions.", file=sys.stderr)
        return 1

    with open(session_file, encoding="utf-8") as f:
        session = json.load(f)

    # Check if implementable
    if not session.get("implementable", False):
        print("Error: session %s is not implementable (resolution: %s)" % (
            session_id, session.get("resolution", "?")), file=sys.stderr)
        print("Only ADOPT and ADOPT_WITH_DISSENT sessions can be implemented.", file=sys.stderr)
        return 1

    try:
        executor = _resolve_implement_executor(session, executor, session_id)
    except ValueError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1

    # Check lock
    lock_file = os.path.join(project_dir, ".alpha-omega", "sessions", "%s.lock.json" % session_id)
    if os.path.isfile(lock_file):
        with open(lock_file, encoding="utf-8") as f:
            lock_info = json.load(f)
        print("Error: session %s is locked by %s at %s" % (
            session_id, lock_info.get("executor", "?"), lock_info.get("started", "?")),
            file=sys.stderr)
        print("Use --force to override.", file=sys.stderr)
        if not args.force:
            return 1
        print("Forcing lock override...", file=sys.stderr)

    # Acquire lock
    import time as _time
    lock_data = {
        "executor": executor,
        "started": _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime()),
        "pid": os.getpid(),
    }
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(lock_data, f, indent=2)

    try:
        # Build implementation prompt
        brief = session.get("implementation_brief", {})
        prompt = _build_implement_prompt(brief, executor, project_dir)

        print("=" * 60)
        print("Alpha-Omega Implementation")
        print("=" * 60)
        print("Session: %s" % session_id)
        print("Executor: %s (%s)" % (executor.upper(), "Claude" if executor == "alpha" else "Codex"))
        print("Resolution: %s" % session.get("resolution", "?"))
        print("Winning option: %s" % session.get("winning_option", "?"))
        print("=" * 60)
        print()

        # Run implementation
        timeout = args.timeout or config["implement_timeout"]
        if executor == "alpha":
            model = args.model or config["alpha_model"]
            result = run_alpha(prompt, timeout=timeout, model=model,
                               work_dir=project_dir,
                               max_turns=config["implement_max_turns"],
                               phase="implement")
        else:
            result = run_omega(prompt, timeout=timeout,
                               work_dir=project_dir, phase="implement")

        # Parse completion report
        report = parse_json_response(result.text, source=executor)
        if not report.get("_parse_ok"):
            report = {
                "status": "partial" if result.ok else "failed",
                "summary": result.text[:2000] if result.text else (result.error or "No output"),
                "files_changed": [],
                "commands_ran": [],
                "blockers": [result.error] if result.error else [],
                "next_steps": [],
            }

        # Record attempt
        attempt = {
            "executor": executor,
            "timestamp": _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime()),
            "status": report.get("status", "unknown"),
            "summary": report.get("summary", ""),
            "files_changed": report.get("files_changed", []),
            "commands_ran": report.get("commands_ran", []),
            "blockers": report.get("blockers", []),
            "next_steps": report.get("next_steps", []),
            "duration_s": round(result.duration, 1),
        }
        session.setdefault("attempts", []).append(attempt)

        # Save updated session
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, default=str)
    finally:
        # Always release lock
        try:
            os.remove(lock_file)
        except OSError:
            pass

    # Show results
    print()
    print("=" * 60)
    print("Implementation Result: %s" % attempt["status"].upper())
    print("=" * 60)
    print()

    if attempt.get("summary"):
        print(attempt["summary"][:3000])
        print()

    if attempt.get("files_changed"):
        print("Files changed:")
        for f_name in attempt["files_changed"]:
            print("  %s" % f_name)
        print()

    if attempt.get("blockers"):
        print("Blockers:")
        for b in attempt["blockers"]:
            print("  - %s" % b)
        print()

    if attempt.get("next_steps"):
        print("Next steps:")
        for s in attempt["next_steps"]:
            print("  - %s" % s)
        print()

    # Show git diff stat
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        if diff_result.stdout.strip():
            print("Git changes:")
            print(diff_result.stdout)
    except Exception:
        pass

    print("Duration: %.1fs" % result.duration)
    print("Session updated: %s" % session_file)

    return 0 if attempt["status"] == "completed" else 1


def _resolve_implement_executor(session, executor, session_id):
    """Resolve implement executor, failing on ambiguous winner-based selection."""
    if executor != "winner":
        return executor

    winning_brain = session.get("winning_brain")
    if winning_brain in ("alpha", "omega"):
        return winning_brain

    raise ValueError(
        "session %s has ambiguous winning_brain=%r; rerun with --executor alpha or --executor omega." % (
            session_id, winning_brain)
    )


def _build_implement_prompt(brief, executor, project_dir):
    """Build focused implementation prompt — code, not debate."""
    role = "Alpha (Claude)" if executor == "alpha" else "Omega (Codex)"

    parts = []
    parts.append("# Implementation Task")
    parts.append("")
    parts.append("You are %s. A dual-brain debate has concluded. Your job now is to" % role)
    parts.append("IMPLEMENT the winning solution. Do NOT re-debate or suggest alternatives.")
    parts.append("")
    parts.append("## Resolution")
    parts.append("")
    parts.append("**Winning option:** %s" % brief.get("winning_option", ""))
    parts.append("**What it is:** %s" % brief.get("winning_thesis", ""))
    parts.append("**Goal:** %s" % brief.get("goal", ""))
    parts.append("")

    if brief.get("dissent"):
        parts.append("**Dissent recorded:** %s" % brief["dissent"])
        parts.append("(Address this concern if possible, but do not change the winning approach.)")
        parts.append("")

    if brief.get("constraints"):
        parts.append("## Constraints")
        for c in brief["constraints"]:
            parts.append("- %s" % c)
        parts.append("")

    if brief.get("open_questions"):
        parts.append("## Open Questions (resolve as you go)")
        for q in brief["open_questions"]:
            parts.append("- %s" % q)
        parts.append("")

    parts.append("## Instructions")
    parts.append("")
    parts.append("1. Read the relevant files in the project")
    parts.append("2. Edit code to implement the winning option")
    parts.append("3. Run any relevant tests or checks")
    parts.append("4. When done, output a JSON completion report:")
    parts.append("")
    parts.append("```json")
    parts.append('{')
    parts.append('    "status": "completed|partial|failed",')
    parts.append('    "summary": "1-3 sentences of what you did",')
    parts.append('    "files_changed": ["path/to/file1.py", "path/to/file2.py"],')
    parts.append('    "commands_ran": ["pytest tests/", "python -m myapp"],')
    parts.append('    "checks": ["tests pass", "no import errors"],')
    parts.append('    "blockers": ["list any issues preventing completion"],')
    parts.append('    "next_steps": ["what remains to be done, if anything"]')
    parts.append('}')
    parts.append("```")
    parts.append("")
    parts.append("IMPORTANT: Write code, edit files, run commands. Do NOT just describe")
    parts.append("what should be done — actually do it. End with the JSON report above.")

    return "\n".join(parts)


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

    _write_ao_gitignore(ao_dir)

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

    # CLAUDE.md (for Alpha/Claude) — only if it doesn't exist
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if not os.path.isfile(claude_md):
        project_name = os.path.basename(os.path.abspath(project_dir))
        with open(claude_md, "w", encoding="utf-8") as f:
            f.write("# %s\n\n" % project_name)
            f.write("## What this project is\n\n")
            f.write("<!-- TODO: Describe what this project does -->\n\n")
            f.write("## Architecture\n\n")
            f.write("<!-- TODO: Key files, modules, how things connect -->\n\n")
            f.write("## Commands\n\n")
            f.write("<!-- TODO: How to build, test, run -->\n\n")
            f.write("## Constraints\n\n")
            f.write("<!-- TODO: Language version, dependencies, rules -->\n\n")
        print("Created CLAUDE.md (Alpha's memory — fill in the TODOs)")

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


def cmd_recall(args):
    """Search past decisions, debates, and reviews."""
    from .memory import build_index, recall

    project_dir = args.project or os.getcwd()
    ao_dir = os.path.join(project_dir, ".alpha-omega")

    if not os.path.isdir(ao_dir):
        print("No .alpha-omega/ found. Run 'ao init' first.", file=sys.stderr)
        return 1

    query = " ".join(args.query)
    if not query.strip():
        print("Error: provide a search query", file=sys.stderr)
        return 1

    docs = build_index(ao_dir)
    results = recall(docs, query, max_results=args.last)

    if not results:
        print("No matches for: %s" % query)
        return 0

    print("Results for: %s" % query)
    print("=" * 50)
    print()

    for score, doc in results:
        doc_type = doc.get("type", "?")
        doc_id = doc.get("id", "?")
        resolution = doc.get("resolution", "?")
        winner = doc.get("winning_option")
        question = doc.get("question", "")[:120]
        summary = doc.get("summary", "")[:200]
        timestamp = doc.get("timestamp", "")

        print("[%s] %s  (score: %.2f)" % (doc_type, doc_id, score))
        print("  %s" % timestamp)
        print("  Q: %s" % question)
        if winner:
            print("  Winner: %s (%s)" % (winner, resolution))
        else:
            print("  Verdict: %s" % resolution)
        if summary and summary != question[:200]:
            print("  %s" % summary)
        print()

    print("%d result(s) found." % len(results))
    return 0


def cmd_contradictions(args):
    """Scan decisions for potential contradictions."""
    from .memory import build_index, find_contradictions

    project_dir = args.project or os.getcwd()
    ao_dir = os.path.join(project_dir, ".alpha-omega")

    if not os.path.isdir(ao_dir):
        print("No .alpha-omega/ found. Run 'ao init' first.", file=sys.stderr)
        return 1

    docs = build_index(ao_dir)
    contradictions = find_contradictions(docs)

    if not contradictions:
        print("No contradictions found across %d decisions." % len(docs))
        return 0

    print("Potential Contradictions")
    print("=" * 50)
    print()

    for i, c in enumerate(contradictions, 1):
        c_type = c["type"].replace("_", " ").title()
        a = c["doc_a"]
        b = c["doc_b"]

        print("%d. [%s]" % (i, c_type))
        print("   %s" % c["reason"])
        print()
        print("   A: %s (%s)" % (a["id"], a.get("timestamp", "")))
        print("      Q: %s" % a.get("question", "")[:100])
        if a.get("winning_option"):
            print("      Winner: %s" % a["winning_option"])
        print()
        print("   B: %s (%s)" % (b["id"], b.get("timestamp", "")))
        print("      Q: %s" % b.get("question", "")[:100])
        if b.get("winning_option"):
            print("      Winner: %s" % b["winning_option"])
        print()
        if c.get("shared_topics"):
            print("   Shared topics: %s" % ", ".join(c["shared_topics"]))
        print()

    print("%d potential contradiction(s) found." % len(contradictions))
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

    # setup
    sub.add_parser("setup", help="First-time setup: check prerequisites + init project")

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
                          help="Shared timeout override for both brains (seconds)")
    p_debate.add_argument("--alpha-timeout", type=int, default=None,
                          dest="alpha_timeout",
                          help="Alpha-only timeout (seconds, default: 300 from config)")
    p_debate.add_argument("--omega-timeout", type=int, default=None,
                          dest="omega_timeout",
                          help="Omega-only timeout (seconds, default: 600 from config)")
    p_debate.add_argument("--alpha-max-turns", type=int, default=None,
                          dest="alpha_max_turns",
                          help="Max tool-use turns for Alpha (default: 8 from config)")

    # review
    p_review = sub.add_parser("review", help="Lightweight dual-brain code review")
    p_review.add_argument("--staged", action="store_true",
                          help="Review staged changes (git diff --cached)")
    p_review.add_argument("--branch", default=None,
                          help="Review changes since branch (e.g. main)")
    p_review.add_argument("--save", action="store_true",
                          help="Save review to .alpha-omega/reviews/")
    p_review.add_argument("--model", default=None,
                          help="Alpha model (default: claude-sonnet-4-5)")
    p_review.add_argument("--timeout", type=int, default=None,
                          help="Timeout per brain in seconds (default: 180)")

    # implement
    p_impl = sub.add_parser("implement", help="Implement a debate resolution")
    p_impl.add_argument("session_id", help="Session ID (e.g. ao_1776081171)")
    p_impl.add_argument("--executor", default="winner",
                        choices=["alpha", "omega", "winner"],
                        help="Which brain implements (default: winner)")
    p_impl.add_argument("--model", default=None,
                        help="Alpha model for implementation")
    p_impl.add_argument("--timeout", type=int, default=None,
                        help="Timeout in seconds (default: 900)")
    p_impl.add_argument("--force", action="store_true",
                        help="Override existing lock")

    # recall
    p_recall = sub.add_parser("recall", help="Search past decisions and reviews")
    p_recall.add_argument("query", nargs="+", help="Search query")
    p_recall.add_argument("--last", type=int, default=10, help="Max results")

    # contradictions
    sub.add_parser("contradictions", help="Find contradictions in past decisions")

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
    elif args.command == "review":
        return cmd_review(args)
    elif args.command == "implement":
        return cmd_implement(args)
    elif args.command == "recall":
        return cmd_recall(args)
    elif args.command == "contradictions":
        return cmd_contradictions(args)
    elif args.command == "init":
        return cmd_init(args)
    elif args.command == "history":
        return cmd_history(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "setup":
        return cmd_setup(args)
    else:
        return _show_welcome(args)


if __name__ == "__main__":
    sys.exit(main() or 0)

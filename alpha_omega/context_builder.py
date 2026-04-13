#!/usr/bin/env python3
"""context_builder.py — assembles project context for Alpha-Omega debates.

Scans the current project for relevant files and builds a context pack
that both brains receive as shared evidence before the blind phase.

Python 3.9 compatible.
"""

from __future__ import annotations

import glob
import logging
import os
import subprocess

log = logging.getLogger("ao.context")

# Max chars to include from a single file
MAX_FILE_CHARS = 8000
# Max total context chars
MAX_CONTEXT_CHARS = 40000

# Files to look for (priority order)
CONTEXT_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    ".alpha-omega/INDEX.md",
    ".alpha-omega/decisions.md",
]


def build_context(project_dir=None, extra_files=None):
    """Build a context pack from the current project.

    Returns a structured dict:
    {
        "project_dir": str,
        "project_name": str,
        "files": {relative_path: content_truncated},
        "ao_memory": {relative_path: content},  # .alpha-omega/ files
        "context_text": str,  # formatted markdown for LLM prompts
    }
    """
    if project_dir is None:
        project_dir = os.getcwd()

    project_name = os.path.basename(os.path.abspath(project_dir))

    files = {}
    ao_memory = {}
    total_chars = 0

    # 1. Collect known context files
    for rel_path in CONTEXT_FILES:
        abs_path = os.path.join(project_dir, rel_path)
        if os.path.isfile(abs_path):
            content = _read_truncated(abs_path, MAX_FILE_CHARS)
            if total_chars + len(content) > MAX_CONTEXT_CHARS:
                break
            if rel_path.startswith(".alpha-omega/"):
                ao_memory[rel_path] = content
            else:
                files[rel_path] = content
            total_chars += len(content)

    # 2. Auto-discover project structure and key files
    if total_chars < MAX_CONTEXT_CHARS - 5000:
        scaffold = _build_project_scaffold(project_dir)
        if scaffold:
            files["[project scaffold]"] = scaffold
            total_chars += len(scaffold)

    # 3. Collect .alpha-omega/debates/ (latest 3)
    debates_dir = os.path.join(project_dir, ".alpha-omega", "debates")
    if os.path.isdir(debates_dir):
        debate_files = sorted(
            glob.glob(os.path.join(debates_dir, "*.md")),
            key=os.path.getmtime,
            reverse=True,
        )
        for df in debate_files[:3]:
            rel = os.path.relpath(df, project_dir)
            content = _read_truncated(df, MAX_FILE_CHARS)
            if total_chars + len(content) > MAX_CONTEXT_CHARS:
                break
            ao_memory[rel] = content
            total_chars += len(content)

    # 4. Extra files explicitly requested (contained to project dir)
    if extra_files:
        project_real = os.path.realpath(project_dir)
        for path in extra_files:
            abs_path = path if os.path.isabs(path) else os.path.join(project_dir, path)
            abs_path = os.path.realpath(abs_path)
            if not abs_path.startswith(project_real + os.sep) and abs_path != project_real:
                log.warning("Skipping extra file outside project: %s", path)
                continue
            if os.path.isfile(abs_path):
                rel = os.path.relpath(abs_path, project_dir)
                content = _read_truncated(abs_path, MAX_FILE_CHARS)
                if total_chars + len(content) > MAX_CONTEXT_CHARS:
                    break
                files[rel] = content
                total_chars += len(content)

    # 5. Build formatted context text
    context_text = _format_context(project_name, files, ao_memory)

    return {
        "project_dir": project_dir,
        "project_name": project_name,
        "files": files,
        "ao_memory": ao_memory,
        "context_text": context_text,
    }


# ---------------------------------------------------------------------------
# Review context (git diff based)
# ---------------------------------------------------------------------------

# Include full file content for new/small files under this threshold
_FULL_FILE_MAX_LINES = 100
_MAX_DIFF_CHARS = 30000


def build_review_context(project_dir=None, scope="unstaged"):
    """Build context for ao review from git diff.

    scope:
        "unstaged" — unstaged working tree changes (default)
        "staged"   — staged changes (git diff --cached)
        "branch:X" — all changes since diverging from branch X

    Returns:
        {
            "project_dir": str,
            "scope": str,
            "diff": str,           # unified diff
            "stat": str,           # diffstat summary
            "files_changed": [str],
            "new_files": {path: content},  # full content of new small files
            "context_text": str,    # formatted for LLM prompt
        }
    """
    if project_dir is None:
        project_dir = os.getcwd()

    # Check if we're in a git repo
    git_check = _run_git(["git", "rev-parse", "--git-dir"], project_dir, 200)
    if not git_check.strip():
        log.error("Not a git repository: %s", project_dir)
        return {
            "project_dir": project_dir, "scope": scope, "diff": "",
            "stat": "", "files_changed": [], "new_files": {},
            "context_text": "", "error": "Not a git repository",
        }

    diff_args = _diff_args_for_scope(scope, project_dir)

    # Get diff
    diff = _run_git(["git", "diff", "--unified=3", "--no-ext-diff"] + diff_args,
                    project_dir, _MAX_DIFF_CHARS)

    # Get stat
    stat = _run_git(["git", "diff", "--stat", "--no-ext-diff"] + diff_args,
                    project_dir, 5000)

    # Get list of changed files
    name_only = _run_git(["git", "diff", "--name-only"] + diff_args, project_dir, 5000)
    files_changed = [f for f in name_only.strip().splitlines() if f.strip()]

    # Include untracked files for unstaged scope
    untracked_files = []
    if scope == "unstaged":
        untracked_raw = _run_git(
            ["git", "ls-files", "--others", "--exclude-standard"],
            project_dir, 5000,
        )
        untracked_files = [f for f in untracked_raw.strip().splitlines() if f.strip()]
        files_changed.extend(untracked_files)

    # Get new files — include full content if small
    new_files_raw = _run_git(
        ["git", "diff", "--name-only", "--diff-filter=A"] + diff_args,
        project_dir, 5000,
    )
    new_file_paths = [f for f in new_files_raw.strip().splitlines() if f.strip()]
    # Also treat untracked files as new files
    new_file_paths.extend(untracked_files)
    new_files = {}
    for path in new_file_paths:
        abs_path = os.path.join(project_dir, path)
        if os.path.isfile(abs_path):
            content = _read_truncated(abs_path, MAX_FILE_CHARS)
            line_count = content.count("\n")
            if line_count <= _FULL_FILE_MAX_LINES:
                new_files[path] = content

    # Format context
    parts = []
    parts.append("# Code Review Context\n")
    parts.append("**Scope:** %s\n" % scope)
    parts.append("**Files changed:** %d\n" % len(files_changed))

    if stat:
        parts.append("## Diff Stats\n```\n%s\n```\n" % stat)

    if diff:
        parts.append("## Diff\n```diff\n%s\n```\n" % diff)

    if new_files:
        parts.append("## New Files (full content)\n")
        for path, content in new_files.items():
            parts.append("### %s\n```\n%s\n```\n" % (path, content))

    context_text = "\n".join(parts)

    return {
        "project_dir": project_dir,
        "scope": scope,
        "diff": diff,
        "stat": stat,
        "files_changed": files_changed,
        "new_files": new_files,
        "context_text": context_text,
    }


# ---------------------------------------------------------------------------
# Project scaffold auto-discovery
# ---------------------------------------------------------------------------

# Manifest/config files to auto-include (small, high-signal)
_MANIFEST_FILES = [
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "requirements.txt", "setup.py", "setup.cfg",
    "tsconfig.json", ".eslintrc.json",
]

# Max chars for scaffold section
_SCAFFOLD_BUDGET = 6000


def _build_project_scaffold(project_dir):
    """Build compact project scaffold: directory tree + manifests + entrypoints."""
    parts = []
    budget_left = _SCAFFOLD_BUDGET

    # 1. Directory tree (compact, 2 levels deep)
    tree = _dir_tree(project_dir, max_depth=2)
    if tree:
        tree_text = "Directory structure:\n%s" % tree
        if len(tree_text) < budget_left:
            parts.append(tree_text)
            budget_left -= len(tree_text)

    # 2. Manifest/config files (full content, small files)
    for fname in _MANIFEST_FILES:
        if budget_left < 200:
            break
        fpath = os.path.join(project_dir, fname)
        if os.path.isfile(fpath):
            content = _read_truncated(fpath, min(1500, budget_left))
            if content.strip():
                entry = "%s:\n%s" % (fname, content)
                parts.append(entry)
                budget_left -= len(entry)

    if not parts:
        return ""

    return "\n\n".join(parts)


def _dir_tree(root, max_depth=2, prefix=""):
    """Generate compact directory tree string, skipping hidden/generated dirs."""
    skip_dirs = {
        ".git", ".alpha-omega", "node_modules", "__pycache__", ".venv",
        "venv", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".next", ".nuxt", "target", "vendor", ".idea", ".vscode",
        "egg-info", ".egg-info",
    }
    skip_suffixes = (".pyc", ".pyo", ".egg-info")

    lines = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return ""

    dirs = []
    files = []
    for e in entries:
        if e.startswith(".") and e not in (".env.example",):
            continue
        full = os.path.join(root, e)
        if os.path.isdir(full):
            if e not in skip_dirs and not e.endswith(skip_suffixes):
                dirs.append(e)
        else:
            if not e.endswith(skip_suffixes):
                files.append(e)

    for f in files:
        lines.append("%s%s" % (prefix, f))

    for d in dirs:
        lines.append("%s%s/" % (prefix, d))
        if max_depth > 1:
            sub = _dir_tree(os.path.join(root, d), max_depth - 1, prefix + "  ")
            if sub:
                lines.append(sub)

    return "\n".join(lines) if lines else ""


def _diff_args_for_scope(scope, project_dir):
    """Convert scope string to git diff arguments."""
    if scope == "staged":
        return ["--cached"]
    elif scope.startswith("branch:"):
        branch = scope[7:]
        # Find merge base
        base = _run_git(["git", "merge-base", branch, "HEAD"], project_dir, 200).strip()
        if base:
            return [base, "HEAD"]
        return [branch + "...HEAD"]
    else:  # unstaged
        return []


def _run_git(args, cwd, max_chars):
    """Run a git command, return stdout truncated to max_chars."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, cwd=cwd, timeout=60,
        )
        if result.returncode != 0 and result.stderr.strip():
            log.warning("git command failed (rc=%d): %s — %s",
                        result.returncode, " ".join(args), result.stderr.strip())
        output = result.stdout
        if len(output) > max_chars:
            output = output[:max_chars] + "\n[... truncated at %d chars ...]" % max_chars
        return output
    except Exception as exc:
        log.warning("git command failed: %s — %s", " ".join(args), exc)
        return ""


def _read_truncated(path, max_chars):
    """Read file, truncate if too long."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 100)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... truncated at %d chars ...]" % max_chars
        return content
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return ""


def _format_context(project_name, files, ao_memory):
    """Format all collected context into a single markdown string."""
    parts = []
    parts.append("# Project: %s\n" % project_name)

    if files:
        parts.append("## Project Files\n")
        for rel_path, content in files.items():
            parts.append("### %s\n```\n%s\n```\n" % (rel_path, content))

    if ao_memory:
        parts.append("## Alpha-Omega Memory\n")
        for rel_path, content in ao_memory.items():
            parts.append("### %s\n```\n%s\n```\n" % (rel_path, content))

    return "\n".join(parts)

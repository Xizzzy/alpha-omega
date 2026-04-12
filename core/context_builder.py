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

    # 2. Collect .alpha-omega/debates/ (latest 3)
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

    # 3. Extra files explicitly requested
    if extra_files:
        for path in extra_files:
            abs_path = path if os.path.isabs(path) else os.path.join(project_dir, path)
            if os.path.isfile(abs_path):
                rel = os.path.relpath(abs_path, project_dir)
                content = _read_truncated(abs_path, MAX_FILE_CHARS)
                if total_chars + len(content) > MAX_CONTEXT_CHARS:
                    break
                files[rel] = content
                total_chars += len(content)

    # 4. Build formatted context text
    context_text = _format_context(project_name, files, ao_memory)

    return {
        "project_dir": project_dir,
        "project_name": project_name,
        "files": files,
        "ao_memory": ao_memory,
        "context_text": context_text,
    }


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

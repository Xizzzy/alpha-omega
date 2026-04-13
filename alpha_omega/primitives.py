#!/usr/bin/env python3
"""primitives.py — thin CLI wrappers for Alpha (Claude) and Omega (Codex).

No business logic. No domain knowledge. Just subprocess calls + JSON parsing.
Python 3.9 compatible.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time

log = logging.getLogger("ao.primitives")

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class BrainResult:
    """Result from a brain invocation. Carries output, usage, and diagnostics."""

    __slots__ = ("text", "usage", "duration", "error", "brain", "phase")

    def __init__(self, brain="unknown", phase="unknown"):
        self.text = ""
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
        self.duration = 0.0
        self.error = None  # type: str | None
        self.brain = brain
        self.phase = phase

    @property
    def ok(self):
        return self.error is None and len(self.text) > 0

    def to_dict(self):
        return {
            "brain": self.brain,
            "phase": self.phase,
            "chars": len(self.text),
            "duration_s": round(self.duration, 1),
            "error": self.error,
            "usage": dict(self.usage),
        }


# ---------------------------------------------------------------------------
# Claude CLI wrapper (Alpha)
# ---------------------------------------------------------------------------


def run_alpha(prompt, timeout=300, model="claude-sonnet-4-5", work_dir=None,
              max_turns=3, phase="unknown"):
    """Run Claude CLI non-interactively. Returns BrainResult.

    Alpha = Claude. Uses `claude --print` with JSON output for usage tracking.
    max_turns=3 allows 1-2 file reads + 1 response turn.
    """
    if work_dir is None:
        work_dir = os.getcwd()

    r = BrainResult(brain="Alpha", phase=phase)
    start = time.time()

    cmd = [
        "claude",
        "--print",
        "--model", model,
        "--dangerously-skip-permissions",
        "--no-session-persistence",
        "--max-turns", str(max_turns),
        "--output-format", "json",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
        )
        raw = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        r.duration = time.time() - start
        r.error = "timeout after %ds" % timeout
        log.error("run_alpha: %s", r.error)
        return r
    except FileNotFoundError:
        r.duration = time.time() - start
        r.error = "'claude' not found in PATH"
        log.error("run_alpha: %s", r.error)
        return r
    except Exception as exc:
        r.duration = time.time() - start
        r.error = str(exc)
        log.error("run_alpha error: %s", exc)
        return r

    r.duration = time.time() - start
    log.debug("Alpha returned %d chars in %.1fs", len(raw), r.duration)

    text_output = raw
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict):
            text_output = outer.get("result", raw)
            u = outer.get("usage", {})
            if u:
                r.usage["input_tokens"] = int(u.get("input_tokens", 0))
                r.usage["output_tokens"] = int(u.get("output_tokens", 0))
                r.usage["cached_tokens"] = int(u.get("cache_read_input_tokens", 0))
    except (json.JSONDecodeError, TypeError):
        text_output = raw

    r.text = text_output
    return r


# ---------------------------------------------------------------------------
# Codex CLI wrapper (Omega)
# ---------------------------------------------------------------------------


def run_omega(prompt, timeout=300, work_dir=None, phase="unknown"):
    """Run Codex CLI non-interactively. Returns BrainResult.

    Omega = OpenAI Codex. Uses `codex exec --ephemeral` with stdin pipe.
    Ephemeral: each debate turn is independent, continuity managed by protocol.
    """
    if work_dir is None:
        work_dir = os.getcwd()

    r = BrainResult(brain="Omega", phase=phase)

    # Check auth
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    codex_auth = os.path.expanduser("~/.codex/auth.json")
    if not openai_key and not os.path.isfile(codex_auth):
        r.error = "no Codex auth (no OPENAI_API_KEY, no ~/.codex/auth.json)"
        log.warning("run_omega: %s", r.error)
        return r

    run_env = dict(os.environ)
    if openai_key:
        run_env["OPENAI_API_KEY"] = openai_key

    out_file = "/tmp/ao_omega_%d.txt" % int(time.time() * 1000)

    args = [
        "codex", "exec",
        "--ephemeral",
        "--output-last-message", out_file,
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-C", work_dir,
        "-",
    ]

    start = time.time()
    try:
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        r.duration = time.time() - start
        r.error = "timeout after %ds" % timeout
        log.error("run_omega: %s", r.error)
        return r
    except FileNotFoundError:
        r.duration = time.time() - start
        r.error = "'codex' not found in PATH"
        log.error("run_omega: %s", r.error)
        return r
    except Exception as exc:
        r.duration = time.time() - start
        r.error = str(exc)
        log.error("run_omega error: %s", exc)
        return r

    r.duration = time.time() - start
    log.debug("Omega returned in %.1fs", r.duration)

    raw = ""
    if os.path.isfile(out_file):
        try:
            with open(out_file, encoding="utf-8") as f:
                raw = f.read().strip()
        except OSError:
            pass
        try:
            os.remove(out_file)
        except OSError:
            pass

    if not raw:
        raw = (result.stdout + result.stderr).strip()

    r.text = raw
    return r


# ---------------------------------------------------------------------------
# JSON response parser
# ---------------------------------------------------------------------------


def parse_json_response(raw, source="unknown"):
    """Strip markdown fences, find outermost JSON object, parse it.

    Returns dict with _parse_ok=True on success, or _parse_ok=False on failure.
    """
    if not raw:
        return {"_source": source, "_parse_ok": False, "error": "Empty response"}

    text = raw.strip()

    # Strip markdown code fences
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    # Find outermost JSON object
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        text = text[brace_start:brace_end + 1]

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {"_source": source, "_parse_ok": False, "error": "Not a JSON object"}
        parsed["_source"] = source
        parsed["_parse_ok"] = True
        return parsed
    except json.JSONDecodeError as exc:
        log.warning("%s JSON parse failed: %s", source, exc)
        return {
            "_source": source,
            "_parse_ok": False,
            "error": "JSON parse error: %s" % exc,
            "raw_hint": raw[:500],
        }

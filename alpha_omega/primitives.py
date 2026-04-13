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
# Claude CLI wrapper (Alpha)
# ---------------------------------------------------------------------------


def run_alpha(prompt, timeout=300, model="claude-sonnet-4-5", work_dir=None):
    """Run Claude CLI non-interactively. Returns (text_output, usage_dict).

    Alpha = Claude. Uses `claude --print` with JSON output for usage tracking.
    """
    if work_dir is None:
        work_dir = os.getcwd()

    usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    start = time.time()

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model", model,
                "--dangerously-skip-permissions",
                "--no-session-persistence",
                "--max-turns", "1",
                "--output-format", "json",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
        )
        raw = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        log.error("run_alpha: timed out after %ds", timeout)
        return "", usage
    except FileNotFoundError:
        log.error("run_alpha: 'claude' not found in PATH")
        return "", usage
    except Exception as exc:
        log.error("run_alpha error: %s", exc)
        return "", usage

    duration = time.time() - start
    log.debug("Alpha returned %d chars in %.1fs", len(raw), duration)

    text_output = raw
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict):
            text_output = outer.get("result", raw)
            u = outer.get("usage", {})
            if u:
                usage["input_tokens"] = int(u.get("input_tokens", 0))
                usage["output_tokens"] = int(u.get("output_tokens", 0))
                usage["cached_tokens"] = int(u.get("cache_read_input_tokens", 0))
    except (json.JSONDecodeError, TypeError):
        text_output = raw

    return text_output, usage


# ---------------------------------------------------------------------------
# Codex CLI wrapper (Omega)
# ---------------------------------------------------------------------------


def run_omega(prompt, timeout=300, work_dir=None):
    """Run Codex CLI non-interactively. Returns (text_output, usage_dict).

    Omega = OpenAI Codex. Uses `codex exec --ephemeral` with stdin pipe.
    Ephemeral: each debate turn is independent, continuity managed by protocol.
    """
    if work_dir is None:
        work_dir = os.getcwd()

    usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    out_file = "/tmp/ao_omega_%d.txt" % int(time.time() * 1000)

    # Check auth
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    codex_auth = os.path.expanduser("~/.codex/auth.json")
    if not openai_key and not os.path.isfile(codex_auth):
        log.warning("run_omega: no Codex auth available (no OPENAI_API_KEY, no ~/.codex/auth.json)")
        return "", usage

    run_env = dict(os.environ)
    if openai_key:
        run_env["OPENAI_API_KEY"] = openai_key

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
        log.error("run_omega: timed out after %ds", timeout)
        return "", usage
    except FileNotFoundError:
        log.error("run_omega: 'codex' not found in PATH")
        return "", usage
    except Exception as exc:
        log.error("run_omega error: %s", exc)
        return "", usage

    duration = time.time() - start
    log.debug("Omega returned in %.1fs", duration)

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

    return raw, usage


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

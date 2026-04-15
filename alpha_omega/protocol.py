#!/usr/bin/env python3
"""protocol.py — Alpha-Omega debate protocol orchestrator.

The core of the dual-brain thinking tool.
Implements: blind research -> exchange -> rebuttal -> resolution -> artifacts.

Python 3.9 compatible.
"""

from __future__ import annotations

import json
import logging
import os
import time

from .primitives import run_alpha, run_omega, parse_json_response
from .context_builder import build_context
from .sigma import resolve as sigma_resolve
from .artifacts import generate_artifact_pack

log = logging.getLogger("ao.protocol")

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

BLIND_MEMO_PROMPT = """You are participating in an Alpha-Omega dual-brain design session.

## Your role: {role}

You are one of two genuinely different AI systems analyzing the same problem.
The other brain will analyze it independently — you will NOT see their conclusions
until after you commit yours. This is intentional: different blind spots produce
better outcomes than one brain reviewing another's work.

## Project context

{context}

## The problem / idea to analyze

{question}

## Your task

Analyze this independently. Research if needed. Then produce a STRUCTURED response
as JSON with these exact keys:

```json
{{
    "options": [
        {{
            "name": "short option name",
            "thesis": "1-3 sentences: what this option is and why it works",
            "evidence_quality": 0.0-1.0,
            "constraint_fit": 0.0-1.0,
            "feasibility": 0.0-1.0,
            "reversibility": 0.0-1.0,
            "expected_impact": 0.0-1.0,
            "time_to_learning": 0.0-1.0,
            "pros": ["..."],
            "cons": ["..."]
        }}
    ],
    "recommendation": "name of your recommended option",
    "confidence": 0.0-1.0,
    "assumptions": ["things that must be true for your recommendation to work"],
    "what_would_change_mind": "what evidence would make you switch to a different option",
    "open_questions": ["things you don't know that matter"],
    "blind_spots_i_might_have": "honest assessment of what you might be missing"
}}
```

Rules:
- Generate 2-4 options (not just one)
- Score each option honestly (don't inflate your recommendation)
- The "blind_spots_i_might_have" field is critical — this is what the other brain will check
- You may read project files if the question is about specific code or architecture
- Be concrete, not abstract. Names, numbers, architectures — not "consider various approaches"
- Your FINAL output MUST be the JSON object above — always end with it
"""

CRITIQUE_PROMPT = """You are in the CRITIQUE phase of an Alpha-Omega debate.

## Your role: {role}

You previously submitted your independent memo (below). Now you can see
the other brain's memo. Your job is NOT to agree or disagree reflexively.

## Your task

1. **Steelman first**: show you understand the other brain's position charitably
2. **Then critique**: what did they miss? What blind spots do you see?
3. **Concede where warranted**: if they found something you missed, say so explicitly
4. **Final position**: do you change your recommendation, or hold?

## Your original memo
```json
{own_memo}
```

## The other brain's memo
```json
{other_memo}
```

Respond as JSON:
```json
{{
    "steelman": "1-2 sentences: the strongest version of their argument",
    "critiques": [
        {{
            "text": "what they missed or got wrong",
            "severity": "minor|moderate|major",
            "evidence": "why you believe this"
        }}
    ],
    "concessions": [
        {{
            "text": "what they found that you missed",
            "impact": "how this changes your analysis"
        }}
    ],
    "final_recommendation": "your updated recommendation (may be same or changed)",
    "confidence": 0.0-1.0,
    "resolution_suggestion": "ADOPT|ADOPT_WITH_DISSENT|RUN_EXPERIMENT|NEEDS_USER_CHOICE"
}}
```

Rules:
- You MUST steelman before critiquing (show you understood their position)
- Empty concessions list = you learned nothing from them. This is unlikely — be honest.
- If their option is genuinely better, switch. Ego is not a design criterion.
- You may read project files if needed to verify claims or check code
- Your FINAL output MUST be the JSON object above — always end with it
"""

# ---------------------------------------------------------------------------
# Session class
# ---------------------------------------------------------------------------


class DebateSession:
    """Orchestrates a single Alpha-Omega debate session."""

    def __init__(self, question, project_dir=None, extra_files=None, mode="explore",
                 model=None, timeout=None, alpha_timeout=None, omega_timeout=None,
                 alpha_max_turns=None):
        self.question = question
        self.project_dir = project_dir or os.getcwd()
        self.extra_files = extra_files or []
        self.mode = mode  # explore | specify | build | audit
        self.model = model or "claude-sonnet-4-5"
        # Per-brain timeouts; legacy `timeout=` is a fallback for external callers.
        self.alpha_timeout = alpha_timeout or timeout or 300
        self.omega_timeout = omega_timeout or timeout or 600
        self.alpha_max_turns = alpha_max_turns or 8
        # Kept for backward compat with any code reading session.timeout directly.
        self.timeout = self.alpha_timeout
        self.session_id = "ao_%d" % int(time.time())

        self.context = None
        self.alpha_memo = None
        self.omega_memo = None
        self.alpha_critique = None
        self.omega_critique = None
        self.sigma_result = None
        self.artifact_pack = None

        # Diagnostics
        self._diagnostics = []  # list of BrainResult.to_dict()
        self._phase_times = {}
        self._start_time = time.time()

    def run(self):
        """Execute the full debate protocol. Returns artifact pack dict."""
        log.info("=== AO Session %s started ===", self.session_id)
        log.info("Question: %s", self.question[:200])
        log.info("Model: %s, Alpha timeout: %ds (max_turns=%d), Omega timeout: %ds",
                 self.model, self.alpha_timeout, self.alpha_max_turns, self.omega_timeout)

        # Phase 1: Build context
        phase_start = time.time()
        log.info("Phase 1: Building project context...")
        self.context = build_context(self.project_dir, self.extra_files)
        self._phase_times["context"] = time.time() - phase_start

        # Phase 2: Blind independent research
        phase_start = time.time()
        log.info("Phase 2: Blind independent memos...")
        self.alpha_memo = self._get_blind_memo("Alpha")
        self.omega_memo = self._get_blind_memo("Omega")
        self._phase_times["blind"] = time.time() - phase_start

        # Graceful degradation: if both fail, still try to produce useful output
        both_failed = (
            not self.alpha_memo.get("_parse_ok")
            and not self.omega_memo.get("_parse_ok")
        )
        if both_failed:
            alpha_empty = not self.alpha_memo.get("raw_text", "").strip()
            omega_empty = not self.omega_memo.get("raw_text", "").strip()
            if alpha_empty and omega_empty:
                log.error("Both brains returned empty responses. Aborting.")
                return {
                    "error": "Both brains failed to respond",
                    "alpha_raw": self.alpha_memo,
                    "omega_raw": self.omega_memo,
                    "diagnostics": self._diagnostics,
                }
            log.warning("Both memos failed JSON parse. Continuing with raw text fallback.")

        # Phase 3: Cross-examination
        phase_start = time.time()
        log.info("Phase 3: Cross-examination...")
        self.alpha_critique = self._get_critique("Alpha", self.alpha_memo, self.omega_memo)
        self.omega_critique = self._get_critique("Omega", self.omega_memo, self.alpha_memo)
        self._phase_times["critique"] = time.time() - phase_start

        # Phase 4: Sigma resolution
        phase_start = time.time()
        log.info("Phase 4: Design Sigma resolution...")
        debate_rounds = self._build_debate_rounds()
        self.sigma_result = sigma_resolve(self.alpha_memo, self.omega_memo, debate_rounds)
        log.info("Resolution: %s", self.sigma_result.get("resolution"))
        self._phase_times["sigma"] = time.time() - phase_start

        # Phase 5: Generate artifact pack
        phase_start = time.time()
        log.info("Phase 5: Generating artifact pack...")
        self.artifact_pack = generate_artifact_pack(
            question=self.question,
            alpha_memo=self.alpha_memo,
            omega_memo=self.omega_memo,
            alpha_critique=self.alpha_critique,
            omega_critique=self.omega_critique,
            sigma_result=self.sigma_result,
            mode=self.mode,
            session_id=self.session_id,
            diagnostics=self._build_diagnostics_summary(),
        )
        self._phase_times["artifacts"] = time.time() - phase_start

        duration = time.time() - self._start_time
        log.info("=== AO Session %s completed in %.0fs ===", self.session_id, duration)

        return self.artifact_pack

    def _get_blind_memo(self, role):
        """Get independent memo from one brain (blind phase)."""
        prompt = BLIND_MEMO_PROMPT.format(
            role=role,
            context=self.context["context_text"],
            question=self.question,
        )

        log.info("Requesting blind memo from %s...", role)
        if role == "Alpha":
            result = run_alpha(prompt, timeout=self.alpha_timeout, model=self.model,
                               work_dir=self.project_dir,
                               max_turns=self.alpha_max_turns,
                               phase="blind_memo")
        else:
            result = run_omega(prompt, timeout=self.omega_timeout,
                               work_dir=self.project_dir, phase="blind_memo")

        self._diagnostics.append(result.to_dict())
        log.info("%s memo: %d chars in %.1fs%s",
                 role, len(result.text), result.duration,
                 " [ERROR: %s]" % result.error if result.error else "")

        if not result.ok:
            log.warning("%s blind memo failed: %s", role, result.error or "empty response")
            return {
                "_source": role,
                "_parse_ok": False,
                "_error": result.error,
                "options": [],
                "recommendation": "",
                "confidence": 0.3,
                "assumptions": [],
                "what_would_change_mind": "",
                "open_questions": [],
                "raw_text": result.text[:3000],
            }

        parsed = parse_json_response(result.text, source=role)
        if not parsed.get("_parse_ok"):
            log.warning("%s memo failed to parse as JSON, using raw text", role)
            parsed = {
                "_source": role,
                "_parse_ok": False,
                "options": [],
                "recommendation": "",
                "confidence": 0.3,
                "assumptions": [],
                "what_would_change_mind": "",
                "open_questions": [],
                "raw_text": result.text[:3000],
            }
        return parsed

    def _get_critique(self, role, own_memo, other_memo):
        """Get critique from one brain after seeing the other's memo."""
        # Sanitize memos for prompt (remove internal fields)
        own_clean = {k: v for k, v in own_memo.items() if not k.startswith("_")}
        other_clean = {k: v for k, v in other_memo.items() if not k.startswith("_")}

        prompt = CRITIQUE_PROMPT.format(
            role=role,
            own_memo=json.dumps(own_clean, indent=2, default=str),
            other_memo=json.dumps(other_clean, indent=2, default=str),
        )

        log.info("Requesting critique from %s...", role)
        if role == "Alpha":
            result = run_alpha(prompt, timeout=self.alpha_timeout, model=self.model,
                               work_dir=self.project_dir,
                               max_turns=self.alpha_max_turns,
                               phase="critique")
        else:
            result = run_omega(prompt, timeout=self.omega_timeout,
                               work_dir=self.project_dir, phase="critique")

        self._diagnostics.append(result.to_dict())
        log.info("%s critique: %d chars in %.1fs%s",
                 role, len(result.text), result.duration,
                 " [ERROR: %s]" % result.error if result.error else "")

        if not result.ok:
            log.warning("%s critique failed: %s", role, result.error or "empty response")
            return {
                "_source": role,
                "_parse_ok": False,
                "_error": result.error,
                "steelman": "",
                "critiques": [],
                "concessions": [],
                "final_recommendation": own_memo.get("recommendation", ""),
                "confidence": own_memo.get("confidence", 0.5),
                "raw_text": result.text[:3000],
            }

        parsed = parse_json_response(result.text, source=role)
        if not parsed.get("_parse_ok"):
            log.warning("%s critique failed to parse, using empty", role)
            parsed = {
                "_source": role,
                "_parse_ok": False,
                "steelman": "",
                "critiques": [],
                "concessions": [],
                "final_recommendation": own_memo.get("recommendation", ""),
                "confidence": own_memo.get("confidence", 0.5),
                "raw_text": result.text[:3000],
            }
        return parsed

    def _build_debate_rounds(self):
        """Structure debate data for Sigma."""
        rounds = []
        if self.alpha_critique:
            rounds.append({
                "speaker": "alpha",
                "critiques": self.alpha_critique.get("critiques", []),
                "concessions": self.alpha_critique.get("concessions", []),
            })
        if self.omega_critique:
            rounds.append({
                "speaker": "omega",
                "critiques": self.omega_critique.get("critiques", []),
                "concessions": self.omega_critique.get("concessions", []),
            })
        return rounds

    def _build_diagnostics_summary(self):
        """Build diagnostics for the artifact pack."""
        total_duration = time.time() - self._start_time
        total_input = sum(d.get("usage", {}).get("input_tokens", 0) for d in self._diagnostics)
        total_output = sum(d.get("usage", {}).get("output_tokens", 0) for d in self._diagnostics)
        errors = [d for d in self._diagnostics if d.get("error")]

        return {
            "total_duration_s": round(total_duration, 1),
            "phase_times": {k: round(v, 1) for k, v in self._phase_times.items()},
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "calls": len(self._diagnostics),
            "errors": len(errors),
            "error_details": [
                "%s/%s: %s" % (d["brain"], d["phase"], d["error"])
                for d in errors
            ],
            "per_call": self._diagnostics,
        }

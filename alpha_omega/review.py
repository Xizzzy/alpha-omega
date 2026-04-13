#!/usr/bin/env python3
"""review.py — lightweight code review protocol.

Blind memos + review_sigma. No critique phase unless escalated.
Based on NeurIPS 2025 finding: ensemble diversity > debate rounds.

Python 3.9 compatible.
"""

from __future__ import annotations

import json
import logging
import time

from .primitives import run_alpha, run_omega, parse_json_response

log = logging.getLogger("ao.review")

# ---------------------------------------------------------------------------
# Review memo prompt
# ---------------------------------------------------------------------------

REVIEW_MEMO_PROMPT = """You are reviewing code changes as {role} in an Alpha-Omega dual-brain review.

The other brain is reviewing the same changes independently — you will NOT see
their assessment. Give your honest, independent review.

## Code Changes

{context}

## Your task

Review these changes and produce a JSON response:

```json
{{
    "merge_recommendation": "safe|risky|needs-debate",
    "confidence": 0.0-1.0,
    "risks": [
        {{
            "description": "what could go wrong",
            "severity": "low|medium|high|critical",
            "file": "path/to/file (if specific)"
        }}
    ],
    "missing_tests": ["descriptions of tests that should exist but don't"],
    "blind_spots": "what you might be missing in this review",
    "summary": "1-2 sentence overall assessment"
}}
```

Rules:
- Focus on RISKS and BLIND SPOTS, not style
- "safe" = no significant concerns, fine to merge
- "risky" = has concerns that should be addressed before merge
- "needs-debate" = complex enough to warrant a full Alpha-Omega debate
- Be concrete: file names, line numbers, specific concerns
- Empty risks list with "safe" is fine if the changes are genuinely low-risk
"""

# ---------------------------------------------------------------------------
# Review sigma (deterministic, no LLM)
# ---------------------------------------------------------------------------

# Escalation thresholds
_ESCALATE_CONFIDENCE = 0.5     # below this → auto-escalate
_SAFE_CONFIDENCE = 0.7         # both above this + both safe → skip critique


def review_sigma(alpha_memo, omega_memo):
    """Deterministic review resolution. No LLM calls.

    Returns:
        {
            "verdict": "safe|risky|needs-debate",
            "agreement": "agree|partial|disagree",
            "should_escalate": bool,
            "escalation_reason": str or None,
            "risks": [...],        # merged, deduplicated
            "missing_tests": [...],
            "alpha_summary": str,
            "omega_summary": str,
            "dissent": str or None,
        }
    """
    a_rec = alpha_memo.get("merge_recommendation", "risky")
    o_rec = omega_memo.get("merge_recommendation", "risky")
    a_conf = float(alpha_memo.get("confidence", 0.5))
    o_conf = float(omega_memo.get("confidence", 0.5))

    # Merge risks (deduplicate by description similarity)
    all_risks = []
    seen = set()
    for memo in [alpha_memo, omega_memo]:
        for risk in memo.get("risks", []):
            desc = risk.get("description", "").lower().strip()
            if desc and desc not in seen:
                seen.add(desc)
                all_risks.append(risk)

    # Merge missing tests
    all_tests = []
    test_seen = set()
    for memo in [alpha_memo, omega_memo]:
        for t in memo.get("missing_tests", []):
            tl = t.lower().strip()
            if tl and tl not in test_seen:
                test_seen.add(tl)
                all_tests.append(t)

    # Determine agreement
    if a_rec == o_rec:
        agreement = "agree"
    elif {a_rec, o_rec} == {"safe", "risky"}:
        agreement = "partial"
    else:
        agreement = "disagree"

    # Determine verdict and escalation
    should_escalate = False
    escalation_reason = None
    dissent = None

    # Both low confidence → escalate
    if a_conf < _ESCALATE_CONFIDENCE and o_conf < _ESCALATE_CONFIDENCE:
        should_escalate = True
        escalation_reason = "Both brains have low confidence (Alpha: %.2f, Omega: %.2f)" % (a_conf, o_conf)

    # Either says needs-debate → escalate
    if a_rec == "needs-debate" or o_rec == "needs-debate":
        should_escalate = True
        escalation_reason = "%s recommends full debate" % (
            "Both brains" if a_rec == o_rec else ("Alpha" if a_rec == "needs-debate" else "Omega"))

    # Disagree on safe vs risky → record dissent
    if agreement == "partial":
        safe_brain = "Alpha" if a_rec == "safe" else "Omega"
        risky_brain = "Alpha" if a_rec == "risky" else "Omega"
        dissent = "%s says safe, %s says risky" % (safe_brain, risky_brain)
        # Escalate if confidence gap is also large
        if abs(a_conf - o_conf) > 0.3:
            should_escalate = True
            escalation_reason = "Divergent recommendations with large confidence gap"

    # Full disagree → escalate
    if agreement == "disagree":
        should_escalate = True
        escalation_reason = "Fundamental disagreement: Alpha=%s, Omega=%s" % (a_rec, o_rec)
        dissent = "Alpha: %s (%.2f), Omega: %s (%.2f)" % (a_rec, a_conf, o_rec, o_conf)

    # Determine final verdict
    if should_escalate:
        verdict = "needs-debate"
    elif agreement == "agree":
        verdict = a_rec  # both agree
    else:
        # Partial agreement: go with the more cautious one
        verdict = "risky"

    # Sort risks by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_risks.sort(key=lambda r: severity_order.get(r.get("severity", "medium"), 2))

    return {
        "verdict": verdict,
        "agreement": agreement,
        "should_escalate": should_escalate,
        "escalation_reason": escalation_reason,
        "risks": all_risks[:10],  # top 10
        "missing_tests": all_tests[:5],
        "alpha_summary": alpha_memo.get("summary", ""),
        "omega_summary": omega_memo.get("summary", ""),
        "dissent": dissent,
    }


# ---------------------------------------------------------------------------
# Review session
# ---------------------------------------------------------------------------


class ReviewSession:
    """Lightweight review: blind memos + review_sigma. No critique."""

    def __init__(self, review_context, model=None, timeout=None):
        self.review_context = review_context
        self.model = model or "claude-sonnet-4-5"
        self.timeout = timeout or 180  # shorter than debate
        self.session_id = "aor_%d" % int(time.time())

        self._diagnostics = []
        self._start_time = time.time()

    def run(self):
        """Run blind review. Returns review result dict."""
        log.info("=== AO Review %s started ===", self.session_id)

        context_text = self.review_context["context_text"]
        if not context_text.strip() or not self.review_context.get("diff", "").strip():
            return {"error": "No changes to review"}

        project_dir = self.review_context.get("project_dir")

        # Blind memos
        log.info("Requesting review from Alpha...")
        alpha_result = run_alpha(
            REVIEW_MEMO_PROMPT.format(role="Alpha", context=context_text),
            timeout=self.timeout, model=self.model,
            work_dir=project_dir, phase="review",
        )
        self._diagnostics.append(alpha_result.to_dict())
        alpha_memo = self._parse_review_memo(alpha_result, "Alpha")

        log.info("Requesting review from Omega...")
        omega_result = run_omega(
            REVIEW_MEMO_PROMPT.format(role="Omega", context=context_text),
            timeout=self.timeout,
            work_dir=project_dir, phase="review",
        )
        self._diagnostics.append(omega_result.to_dict())
        omega_memo = self._parse_review_memo(omega_result, "Omega")

        # Review sigma
        sigma = review_sigma(alpha_memo, omega_memo)

        duration = time.time() - self._start_time
        log.info("=== AO Review %s: %s in %.0fs ===",
                 self.session_id, sigma["verdict"].upper(), duration)

        return {
            "session_id": self.session_id,
            "scope": self.review_context.get("scope", ""),
            "files_changed": self.review_context.get("files_changed", []),
            "verdict": sigma["verdict"],
            "agreement": sigma["agreement"],
            "should_escalate": sigma["should_escalate"],
            "escalation_reason": sigma.get("escalation_reason"),
            "risks": sigma["risks"],
            "missing_tests": sigma["missing_tests"],
            "dissent": sigma.get("dissent"),
            "alpha_summary": sigma.get("alpha_summary", ""),
            "omega_summary": sigma.get("omega_summary", ""),
            "duration_s": round(duration, 1),
            "diagnostics": self._diagnostics,
        }

    def _parse_review_memo(self, brain_result, role):
        """Parse review memo from brain output."""
        if not brain_result.ok:
            log.warning("%s review failed: %s", role, brain_result.error)
            return {
                "merge_recommendation": "risky",
                "confidence": 0.3,
                "risks": [],
                "missing_tests": [],
                "blind_spots": "Review failed: %s" % (brain_result.error or "empty response"),
                "summary": "Review failed",
            }

        parsed = parse_json_response(brain_result.text, source=role)
        if not parsed.get("_parse_ok"):
            log.warning("%s review memo failed JSON parse", role)
            return {
                "merge_recommendation": "risky",
                "confidence": 0.3,
                "risks": [],
                "missing_tests": [],
                "blind_spots": "JSON parse failed",
                "summary": brain_result.text[:200] if brain_result.text else "No output",
            }

        return parsed

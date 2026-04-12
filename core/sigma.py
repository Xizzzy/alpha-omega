#!/usr/bin/env python3
"""sigma.py — Design Sigma: deterministic resolver for Alpha-Omega debates.

No LLM calls. Pure scoring of structured debate output.
Evaluates QUALITY of arguments, not just agreement/disagreement.

Python 3.9 compatible.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ao.sigma")

# ---------------------------------------------------------------------------
# Resolution states
# ---------------------------------------------------------------------------

# Unlike trading Sigma (APPROVED/REJECTED), Design Sigma has richer outcomes
# because design decisions often depend on user values, not just logic.

RESOLUTION_STATES = {
    "ADOPT",                  # Strong consensus, clear winner
    "ADOPT_WITH_DISSENT",     # Winner exists, but valid minority concern recorded
    "RUN_EXPERIMENT",         # Both options plausible, need data to decide
    "NEEDS_USER_CHOICE",      # Depends on user's priorities/values, not logic
    "INSUFFICIENT_EVIDENCE",  # Neither brain had strong enough evidence
    "DEADLOCK",               # Fundamental disagreement, no resolution
}


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

# These weights determine how Sigma evaluates option quality.
# Tuned for design decisions (not trading actions).

WEIGHTS = {
    "evidence_quality": 0.30,     # How well-sourced are the claims?
    "constraint_fit": 0.20,       # Does it fit stated constraints?
    "feasibility": 0.15,          # Can it actually be built/done?
    "reversibility": 0.15,        # Can we undo if wrong?
    "expected_impact": 0.10,      # How big is the upside?
    "time_to_learning": 0.10,     # How fast do we learn if it works?
}


def score_option(option):
    """Score a single option from a debate.

    option should be a dict with keys matching WEIGHTS (each 0.0-1.0).
    Returns float in [0, 1].
    """
    total = 0.0
    for key, weight in WEIGHTS.items():
        val = float(option.get(key, 0.5))
        val = max(0.0, min(1.0, val))
        total += weight * val
    return round(total, 4)


def resolve(alpha_memo, omega_memo, debate_rounds):
    """Deterministic Design Sigma resolution.

    Args:
        alpha_memo: dict — Alpha's structured output
            {
                "options": [{"name": str, "thesis": str, evidence_quality: float, ...}],
                "recommendation": str,
                "confidence": float,
                "assumptions": [str],
                "what_would_change_mind": str,
            }
        omega_memo: dict — Omega's structured output (same shape)
        debate_rounds: list of dicts — exchange/rebuttal history
            [{"speaker": "alpha"|"omega", "critiques": [...], "concessions": [...]}]

    Returns:
        {
            "resolution": str (one of RESOLUTION_STATES),
            "winning_option": str or None,
            "score_alpha": float,
            "score_omega": float,
            "agreement_level": float (0-1),
            "reasoning": str,
            "dissent": str or None,
            "open_questions": [str],
        }
    """
    # --- Score each side's recommended option ---
    alpha_rec = _find_recommended(alpha_memo)
    omega_rec = _find_recommended(omega_memo)

    score_alpha = score_option(alpha_rec) if alpha_rec else 0.0
    score_omega = score_option(omega_rec) if omega_rec else 0.0

    # --- Measure agreement ---
    agreement = _measure_agreement(alpha_memo, omega_memo, debate_rounds)

    # --- Confidence check ---
    alpha_conf = float(alpha_memo.get("confidence", 0.5))
    omega_conf = float(omega_memo.get("confidence", 0.5))

    # --- Resolution logic ---

    # Both low confidence → insufficient evidence
    if alpha_conf < 0.3 and omega_conf < 0.3:
        return _make_result(
            "INSUFFICIENT_EVIDENCE",
            None,
            score_alpha, score_omega, agreement,
            "Both brains have low confidence (Alpha: %.2f, Omega: %.2f). "
            "More research needed before deciding." % (alpha_conf, omega_conf),
            open_questions=_collect_open_questions(alpha_memo, omega_memo),
        )

    # Same recommendation → easy consensus
    alpha_rec_name = (alpha_rec or {}).get("name", "").lower().strip()
    omega_rec_name = (omega_rec or {}).get("name", "").lower().strip()

    if alpha_rec_name and alpha_rec_name == omega_rec_name:
        # Both agree on the same option
        best_score = max(score_alpha, score_omega)
        dissent = _extract_dissent(debate_rounds)
        if dissent and agreement < 0.8:
            return _make_result(
                "ADOPT_WITH_DISSENT",
                alpha_rec_name,
                score_alpha, score_omega, agreement,
                "Both brains recommend '%s' but with noted concerns." % alpha_rec_name,
                dissent=dissent,
            )
        return _make_result(
            "ADOPT",
            alpha_rec_name,
            score_alpha, score_omega, agreement,
            "Strong consensus on '%s'. Alpha score: %.3f, Omega score: %.3f." % (
                alpha_rec_name, score_alpha, score_omega),
        )

    # Different recommendations
    score_gap = abs(score_alpha - score_omega)
    concessions = _count_concessions(debate_rounds)

    # One side conceded during debate
    if concessions.get("alpha", 0) > 0 and concessions.get("omega", 0) == 0:
        winner = omega_rec_name or alpha_rec_name
        return _make_result(
            "ADOPT_WITH_DISSENT",
            winner,
            score_alpha, score_omega, agreement,
            "Alpha conceded to Omega's position '%s' during debate." % winner,
            dissent="Alpha's original position: %s" % alpha_rec_name,
        )
    if concessions.get("omega", 0) > 0 and concessions.get("alpha", 0) == 0:
        winner = alpha_rec_name or omega_rec_name
        return _make_result(
            "ADOPT_WITH_DISSENT",
            winner,
            score_alpha, score_omega, agreement,
            "Omega conceded to Alpha's position '%s' during debate." % winner,
            dissent="Omega's original position: %s" % omega_rec_name,
        )

    # Large score gap → winner with dissent
    if score_gap > 0.15:
        if score_alpha > score_omega:
            winner, loser = alpha_rec_name, omega_rec_name
            winner_score = score_alpha
        else:
            winner, loser = omega_rec_name, alpha_rec_name
            winner_score = score_omega
        return _make_result(
            "ADOPT_WITH_DISSENT",
            winner,
            score_alpha, score_omega, agreement,
            "'%s' scores significantly higher (%.3f vs %.3f). "
            "Omega's concern about '%s' recorded as dissent." % (
                winner, winner_score, min(score_alpha, score_omega), loser),
            dissent="Dissenting option: %s" % loser,
        )

    # Close scores, different recommendations → depends on nature of disagreement
    both_suggest_experiment = (
        _suggests_experiment(alpha_memo) or _suggests_experiment(omega_memo)
    )
    if both_suggest_experiment:
        return _make_result(
            "RUN_EXPERIMENT",
            None,
            score_alpha, score_omega, agreement,
            "Both options score similarly (Alpha: %.3f, Omega: %.3f). "
            "One or both brains suggest experimentation." % (score_alpha, score_omega),
            open_questions=_collect_open_questions(alpha_memo, omega_memo),
        )

    is_value_dependent = _is_value_dependent(debate_rounds)
    if is_value_dependent:
        return _make_result(
            "NEEDS_USER_CHOICE",
            None,
            score_alpha, score_omega, agreement,
            "Disagreement depends on user priorities, not logic. "
            "Alpha prefers '%s', Omega prefers '%s'." % (alpha_rec_name, omega_rec_name),
            open_questions=[
                "Alpha's option '%s': %s" % (alpha_rec_name, (alpha_rec or {}).get("thesis", "")),
                "Omega's option '%s': %s" % (omega_rec_name, (omega_rec or {}).get("thesis", "")),
            ],
        )

    # Fallback: deadlock
    return _make_result(
        "DEADLOCK",
        None,
        score_alpha, score_omega, agreement,
        "Fundamental disagreement. Alpha: '%s' (%.3f), Omega: '%s' (%.3f). "
        "No resolution path found." % (
            alpha_rec_name, score_alpha, omega_rec_name, score_omega),
        open_questions=_collect_open_questions(alpha_memo, omega_memo),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_recommended(memo):
    """Find the recommended option from a memo."""
    if not memo:
        return None
    options = memo.get("options", [])
    rec_name = memo.get("recommendation", "")
    for opt in options:
        if opt.get("name", "").lower().strip() == rec_name.lower().strip():
            return opt
    # Fallback: return first option
    return options[0] if options else None


def _measure_agreement(alpha_memo, omega_memo, rounds):
    """Estimate agreement level (0-1) from debate history."""
    if not rounds:
        return 0.5  # no debate happened

    total_critiques = 0
    total_concessions = 0
    for r in rounds:
        total_critiques += len(r.get("critiques", []))
        total_concessions += len(r.get("concessions", []))

    if total_critiques == 0:
        return 0.9  # no critiques = high agreement

    ratio = total_concessions / (total_critiques + total_concessions)
    return round(min(ratio + 0.3, 1.0), 2)


def _count_concessions(rounds):
    """Count concessions by each speaker."""
    counts = {"alpha": 0, "omega": 0}
    for r in rounds:
        speaker = r.get("speaker", "")
        counts[speaker] = counts.get(speaker, 0) + len(r.get("concessions", []))
    return counts


def _extract_dissent(rounds):
    """Extract unresolved critiques as dissent text."""
    unresolved = []
    for r in rounds:
        for c in r.get("critiques", []):
            if not c.get("resolved", False):
                unresolved.append(c.get("text", ""))
    if unresolved:
        return "; ".join(unresolved[:3])
    return None


def _suggests_experiment(memo):
    """Check if a memo suggests experimentation."""
    rec = memo.get("recommendation", "")
    what_changes = memo.get("what_would_change_mind", "")
    keywords = ("experiment", "test", "pilot", "prototype", "try", "validate", "MVP")
    text = (rec + " " + what_changes).lower()
    return any(kw.lower() in text for kw in keywords)


def _is_value_dependent(rounds):
    """Check if disagreement is about values/priorities rather than facts."""
    keywords = ("priority", "preference", "depends on", "trade-off", "tradeoff",
                "user choice", "business decision", "value judgment")
    for r in rounds:
        for c in r.get("critiques", []):
            text = c.get("text", "").lower()
            if any(kw in text for kw in keywords):
                return True
    return False


def _collect_open_questions(alpha_memo, omega_memo):
    """Collect open questions from both memos."""
    questions = []
    for memo in [alpha_memo, omega_memo]:
        if memo:
            for q in memo.get("open_questions", []):
                if q not in questions:
                    questions.append(q)
    return questions[:5]


def _make_result(resolution, winning_option, score_a, score_o, agreement,
                 reasoning, dissent=None, open_questions=None):
    return {
        "resolution": resolution,
        "winning_option": winning_option,
        "score_alpha": score_a,
        "score_omega": score_o,
        "agreement_level": agreement,
        "reasoning": reasoning,
        "dissent": dissent,
        "open_questions": open_questions or [],
    }

#!/usr/bin/env python3
"""artifacts.py — generates the artifact pack from a completed debate.

Transforms raw debate data into a structured, human-readable deliverable.
Python 3.9 compatible.
"""

from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger("ao.artifacts")


def generate_artifact_pack(question, alpha_memo, omega_memo,
                           alpha_critique, omega_critique,
                           sigma_result, mode="explore", session_id="",
                           diagnostics=None):
    """Generate the final artifact pack from a completed debate.

    Returns dict with:
        markdown: str — full rendered markdown
        decision: dict — structured decision record
        session_id: str
    """
    resolution = sigma_result.get("resolution", "DEADLOCK")
    winning = sigma_result.get("winning_option")
    reasoning = sigma_result.get("reasoning", "")

    # --- Decision record (structured) ---
    decision = {
        "session_id": session_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "question": question,
        "resolution": resolution,
        "winning_option": winning,
        "score_alpha": sigma_result.get("score_alpha", 0),
        "score_omega": sigma_result.get("score_omega", 0),
        "agreement_level": sigma_result.get("agreement_level", 0),
        "reasoning": reasoning,
        "dissent": sigma_result.get("dissent"),
        "open_questions": sigma_result.get("open_questions", []),
        "alpha_recommendation": alpha_memo.get("recommendation", ""),
        "omega_recommendation": omega_memo.get("recommendation", ""),
        "alpha_confidence": alpha_memo.get("confidence", 0),
        "omega_confidence": omega_memo.get("confidence", 0),
        "mode": mode,
    }

    # --- Render markdown ---
    md = _render_markdown(
        question, alpha_memo, omega_memo,
        alpha_critique, omega_critique,
        sigma_result, decision, mode,
        diagnostics=diagnostics,
    )

    return {
        "markdown": md,
        "decision": decision,
        "session_id": session_id,
        "_alpha_memo": alpha_memo,
        "_omega_memo": omega_memo,
    }


def save_to_project(artifact_pack, project_dir):
    """Save debate results to .alpha-omega/ in the project directory."""
    ao_dir = os.path.join(project_dir, ".alpha-omega")
    debates_dir = os.path.join(ao_dir, "debates")
    sessions_dir = os.path.join(ao_dir, "sessions")
    os.makedirs(debates_dir, exist_ok=True)
    os.makedirs(sessions_dir, exist_ok=True)

    session_id = artifact_pack.get("session_id", "unknown")
    decision = artifact_pack.get("decision", {})
    markdown = artifact_pack.get("markdown", "")

    # Save debate transcript
    debate_file = os.path.join(debates_dir, "%s.md" % session_id)
    with open(debate_file, "w", encoding="utf-8") as f:
        f.write(markdown)
    log.info("Debate saved to %s", debate_file)

    # Save structured session JSON (foundation for ao implement)
    session_file = os.path.join(sessions_dir, "%s.json" % session_id)
    session_data = _build_session_json(artifact_pack)
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, default=str)
    log.info("Session JSON saved to %s", session_file)

    # Append to decisions.md
    decisions_file = os.path.join(ao_dir, "decisions.md")
    entry = _format_decision_entry(decision)
    with open(decisions_file, "a", encoding="utf-8") as f:
        f.write("\n" + entry + "\n")
    log.info("Decision appended to %s", decisions_file)

    return debate_file


def _build_session_json(artifact_pack):
    """Build structured session JSON for ao implement."""
    decision = artifact_pack.get("decision", {})
    resolution = decision.get("resolution", "")
    winning_option = decision.get("winning_option")

    # Determine winning brain
    alpha_rec = decision.get("alpha_recommendation", "")
    omega_rec = decision.get("omega_recommendation", "")
    if winning_option:
        w = winning_option.lower().strip()
        if alpha_rec.lower().strip() == w and omega_rec.lower().strip() == w:
            winning_brain = "both"
        elif alpha_rec.lower().strip() == w:
            winning_brain = "alpha"
        elif omega_rec.lower().strip() == w:
            winning_brain = "omega"
        else:
            winning_brain = "unknown"
    else:
        winning_brain = None

    # Build implementation brief from decision data
    brief = {
        "goal": decision.get("question", ""),
        "resolution": resolution,
        "winning_option": winning_option,
        "winning_thesis": "",  # filled from memo options below
        "constraints": [],
        "dissent": decision.get("dissent"),
        "open_questions": decision.get("open_questions", []),
    }

    # Extract winning thesis from memos stored in artifact pack
    for memo_key in ("_alpha_memo", "_omega_memo"):
        memo = artifact_pack.get(memo_key, {})
        if memo:
            for opt in memo.get("options", []):
                if opt.get("name", "").lower().strip() == (winning_option or "").lower().strip():
                    brief["winning_thesis"] = opt.get("thesis", "")
                    brief["constraints"] = opt.get("cons", [])
                    break

    implementable = resolution in ("ADOPT", "ADOPT_WITH_DISSENT")

    return {
        "session_id": decision.get("session_id", ""),
        "timestamp": decision.get("timestamp", ""),
        "question": decision.get("question", ""),
        "resolution": resolution,
        "winning_option": winning_option,
        "winning_brain": winning_brain,
        "implementable": implementable,
        "implementation_brief": brief,
        "scores": {
            "alpha": decision.get("score_alpha", 0),
            "omega": decision.get("score_omega", 0),
            "agreement": decision.get("agreement_level", 0),
        },
        "attempts": [],
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _render_markdown(question, alpha_memo, omega_memo,
                     alpha_critique, omega_critique,
                     sigma_result, decision, mode,
                     diagnostics=None):
    """Render the full artifact pack as markdown."""
    parts = []

    # Header
    parts.append("# Alpha-Omega Design Session")
    parts.append("")
    parts.append("**Date:** %s" % decision.get("timestamp", ""))
    parts.append("**Session:** %s" % decision.get("session_id", ""))
    parts.append("**Mode:** %s" % mode)
    parts.append("")

    # Question
    parts.append("## Question")
    parts.append("")
    parts.append(question)
    parts.append("")

    # Resolution (the most important part — first)
    resolution = sigma_result.get("resolution", "DEADLOCK")
    parts.append("## Resolution: %s" % resolution)
    parts.append("")
    parts.append(sigma_result.get("reasoning", ""))
    parts.append("")

    winning = sigma_result.get("winning_option")
    if winning:
        parts.append("**Winning option:** %s" % winning)
        parts.append("")

    dissent = sigma_result.get("dissent")
    if dissent:
        parts.append("**Dissent:** %s" % dissent)
        parts.append("")

    # Scores
    parts.append("| Metric | Alpha | Omega |")
    parts.append("|--------|-------|-------|")
    parts.append("| Score | %.3f | %.3f |" % (
        sigma_result.get("score_alpha", 0),
        sigma_result.get("score_omega", 0),
    ))
    parts.append("| Confidence | %.2f | %.2f |" % (
        alpha_memo.get("confidence", 0),
        omega_memo.get("confidence", 0),
    ))
    parts.append("| Agreement level | %.2f | |" % sigma_result.get("agreement_level", 0))
    parts.append("")

    # Options from both brains
    parts.append("## Options Considered")
    parts.append("")

    all_options = {}
    for opt in alpha_memo.get("options", []):
        name = opt.get("name", "unnamed")
        all_options[name] = {"alpha": opt}
    for opt in omega_memo.get("options", []):
        name = opt.get("name", "unnamed")
        if name in all_options:
            all_options[name]["omega"] = opt
        else:
            all_options[name] = {"omega": opt}

    for name, sources in all_options.items():
        parts.append("### %s" % name)
        for source_name, opt in sources.items():
            parts.append("")
            parts.append("**%s's view:**" % source_name.capitalize())
            parts.append(opt.get("thesis", ""))
            pros = opt.get("pros", [])
            cons = opt.get("cons", [])
            if pros:
                parts.append("- Pros: %s" % "; ".join(pros))
            if cons:
                parts.append("- Cons: %s" % "; ".join(cons))
        parts.append("")

    # Critique exchange
    parts.append("## Debate Exchange")
    parts.append("")

    if alpha_critique and alpha_critique.get("steelman"):
        parts.append("### Alpha's critique of Omega")
        parts.append("")
        parts.append("**Steelman:** %s" % alpha_critique.get("steelman", ""))
        parts.append("")
        for c in alpha_critique.get("critiques", []):
            parts.append("- [%s] %s" % (c.get("severity", "?"), c.get("text", "")))
        for con in alpha_critique.get("concessions", []):
            parts.append("- *Concession:* %s" % con.get("text", ""))
        parts.append("")

    if omega_critique and omega_critique.get("steelman"):
        parts.append("### Omega's critique of Alpha")
        parts.append("")
        parts.append("**Steelman:** %s" % omega_critique.get("steelman", ""))
        parts.append("")
        for c in omega_critique.get("critiques", []):
            parts.append("- [%s] %s" % (c.get("severity", "?"), c.get("text", "")))
        for con in omega_critique.get("concessions", []):
            parts.append("- *Concession:* %s" % con.get("text", ""))
        parts.append("")

    # Assumptions and risks
    parts.append("## Assumptions")
    parts.append("")
    all_assumptions = set()
    for a in alpha_memo.get("assumptions", []):
        all_assumptions.add(a)
    for a in omega_memo.get("assumptions", []):
        all_assumptions.add(a)
    for a in sorted(all_assumptions):
        parts.append("- %s" % a)
    parts.append("")

    # Open questions
    open_qs = sigma_result.get("open_questions", [])
    if open_qs:
        parts.append("## Open Questions")
        parts.append("")
        for q in open_qs:
            parts.append("- %s" % q)
        parts.append("")

    # Blind spots acknowledged
    parts.append("## Blind Spots Acknowledged")
    parts.append("")
    alpha_blind = alpha_memo.get("blind_spots_i_might_have", "")
    omega_blind = omega_memo.get("blind_spots_i_might_have", "")
    if alpha_blind:
        parts.append("- **Alpha:** %s" % alpha_blind)
    if omega_blind:
        parts.append("- **Omega:** %s" % omega_blind)
    parts.append("")

    # Diagnostics footer
    if diagnostics:
        parts.append("---")
        parts.append("")
        parts.append("<details><summary>Session diagnostics</summary>")
        parts.append("")
        parts.append("| Phase | Duration |")
        parts.append("|-------|----------|")
        for phase, dur in diagnostics.get("phase_times", {}).items():
            parts.append("| %s | %.1fs |" % (phase, dur))
        parts.append("| **Total** | **%.1fs** |" % diagnostics.get("total_duration_s", 0))
        parts.append("")
        parts.append("Tokens: %d in / %d out. Calls: %d." % (
            diagnostics.get("total_input_tokens", 0),
            diagnostics.get("total_output_tokens", 0),
            diagnostics.get("calls", 0),
        ))
        errors = diagnostics.get("error_details", [])
        if errors:
            parts.append("")
            parts.append("**Errors:**")
            for e in errors:
                parts.append("- %s" % e)
        parts.append("")
        parts.append("</details>")
        parts.append("")

    return "\n".join(parts)


def _format_decision_entry(decision):
    """Format a compact decision entry for decisions.md."""
    parts = []
    parts.append("### %s — %s" % (decision.get("session_id", ""), decision.get("timestamp", "")))
    parts.append("")
    parts.append("**Q:** %s" % decision.get("question", "")[:200])
    parts.append("**Resolution:** %s" % decision.get("resolution", ""))
    if decision.get("winning_option"):
        parts.append("**Winner:** %s" % decision["winning_option"])
    parts.append("**Scores:** Alpha %.3f / Omega %.3f / Agreement %.2f" % (
        decision.get("score_alpha", 0),
        decision.get("score_omega", 0),
        decision.get("agreement_level", 0),
    ))
    if decision.get("dissent"):
        parts.append("**Dissent:** %s" % decision["dissent"])
    return "\n".join(parts)

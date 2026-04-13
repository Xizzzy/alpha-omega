#!/usr/bin/env python3
"""memory.py — active memory: recall and contradiction detection.

Canonical index over .alpha-omega/ artifacts.
Deterministic, no LLM calls, stdlib only.

Python 3.9 compatible.
"""

from __future__ import annotations

import json
import logging
import os
import re
import string

log = logging.getLogger("ao.memory")

# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "must", "need", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into", "about",
    "that", "this", "it", "its", "and", "or", "but", "not", "no", "if",
    "then", "than", "so", "up", "out", "all", "each", "both", "few",
    "more", "most", "other", "some", "such", "only", "own", "same",
    "very", "just", "also", "how", "what", "which", "who", "when",
    "where", "why", "we", "our", "they", "their", "them", "you", "your",
    # Russian stop words
    "и", "в", "не", "на", "с", "что", "как", "это", "по", "но",
    "из", "за", "для", "то", "все", "он", "она", "мы", "вы", "они",
    "его", "её", "их", "этот", "эта", "эти", "тот", "та", "те",
    "был", "была", "было", "были", "будет", "быть", "есть",
})


def tokenize(text):
    """Lowercase, strip punctuation, remove stop words."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    words = text.split()
    return [w for w in words if w and w not in _STOP_WORDS and len(w) > 1]


# ---------------------------------------------------------------------------
# Antonym pairs for contradiction detection
# ---------------------------------------------------------------------------

_ANTONYMS = [
    ("python", "node"), ("python", "javascript"), ("python", "typescript"),
    ("monorepo", "microservices"), ("monolith", "microservices"),
    ("sql", "nosql"), ("postgres", "sqlite"), ("postgres", "mongodb"),
    ("rest", "graphql"), ("sync", "async"),
    ("add", "remove"), ("create", "delete"), ("keep", "drop"),
    ("adopt", "reject"), ("accept", "reject"),
    ("simple", "complex"), ("fast", "slow"),
    ("yes", "no"), ("true", "false"),
    ("rewrite", "keep"), ("migrate", "stay"),
]

_ANTONYM_SET = set()
for a, b in _ANTONYMS:
    _ANTONYM_SET.add((a, b))
    _ANTONYM_SET.add((b, a))


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------


def build_index(ao_dir):
    """Build canonical memory index from .alpha-omega/ artifacts.

    Returns list of canonical docs:
    [
        {
            "id": "ao_...",
            "type": "debate" | "review",
            "timestamp": str,
            "question": str,
            "resolution": str,
            "winning_option": str | None,
            "summary": str,
            "tokens": [str],        # tokenized searchable text
            "topic_tokens": [str],  # tokens from question + winning_option only
            "source_files": [str],
        }
    ]
    """
    docs = []
    sessions_dir = os.path.join(ao_dir, "sessions")
    reviews_dir = os.path.join(ao_dir, "reviews")

    # Load session JSONs (debates)
    if os.path.isdir(sessions_dir):
        for fname in sorted(os.listdir(sessions_dir)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(sessions_dir, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    session = json.load(f)
                doc = _session_to_doc(session, path)
                if doc:
                    docs.append(doc)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read session %s: %s", fname, exc)

    # Load review JSONs
    if os.path.isdir(reviews_dir):
        for fname in sorted(os.listdir(reviews_dir)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(reviews_dir, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    review = json.load(f)
                doc = _review_to_doc(review, path)
                if doc:
                    docs.append(doc)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read review %s: %s", fname, exc)

    return docs


def _session_to_doc(session, path):
    """Convert session JSON to canonical doc."""
    sid = session.get("session_id", "")
    if not sid:
        return None

    question = session.get("question", "")
    winning = session.get("winning_option", "") or ""
    resolution = session.get("resolution", "")
    brief = session.get("implementation_brief", {})
    thesis = brief.get("winning_thesis", "")

    searchable = " ".join([question, winning, resolution, thesis])
    topic_text = " ".join([question, winning])

    return {
        "id": sid,
        "type": "debate",
        "timestamp": session.get("timestamp", ""),
        "question": question,
        "resolution": resolution,
        "winning_option": winning or None,
        "summary": thesis or question[:200],
        "tokens": tokenize(searchable),
        "topic_tokens": tokenize(topic_text),
        "source_files": [path],
    }


def _review_to_doc(review, path):
    """Convert review JSON to canonical doc."""
    sid = review.get("session_id", "")
    if not sid:
        return None

    scope = review.get("scope", "")
    verdict = review.get("verdict", "")
    alpha_sum = review.get("alpha_summary", "")
    omega_sum = review.get("omega_summary", "")
    files = review.get("files_changed", [])

    question = "Review (%s): %s" % (scope, ", ".join(files[:5]))
    searchable = " ".join([question, verdict, alpha_sum, omega_sum] + files)

    return {
        "id": sid,
        "type": "review",
        "timestamp": review.get("timestamp", ""),
        "question": question,
        "resolution": verdict,
        "winning_option": None,
        "summary": alpha_sum or omega_sum or verdict,
        "tokens": tokenize(searchable),
        "topic_tokens": tokenize(question),
        "source_files": [path],
    }


# ---------------------------------------------------------------------------
# Recall (search)
# ---------------------------------------------------------------------------

# Field weights for scoring
_WEIGHTS = {
    "question": 3.0,
    "winning_option": 2.5,
    "resolution": 1.5,
    "summary": 1.0,
}


def recall(docs, query, max_results=10):
    """Search docs by query. Returns scored list of (score, doc)."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    query_set = set(query_tokens)
    results = []

    for doc in docs:
        score = 0.0

        # Field-weighted token matching
        for field, weight in _WEIGHTS.items():
            field_text = doc.get(field, "") or ""
            field_tokens = set(tokenize(field_text))
            overlap = query_set & field_tokens
            if overlap:
                score += weight * len(overlap) / max(len(query_set), 1)

        # Bonus for phrase match in question
        q_lower = (doc.get("question", "") or "").lower()
        query_phrase = " ".join(query_tokens)
        if query_phrase in q_lower:
            score += 2.0

        # Bonus for exact token match in winning_option
        w_lower = (doc.get("winning_option", "") or "").lower()
        for qt in query_tokens:
            if qt in w_lower:
                score += 0.5

        if score > 0:
            results.append((round(score, 3), doc))

    results.sort(key=lambda x: x[0], reverse=True)
    return results[:max_results]


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------


def find_contradictions(docs, min_overlap=0.3):
    """Find potential contradictions between resolved debates.

    Only compares debates (not reviews).
    Returns list of:
    {
        "type": "direct_opposite" | "exclusive_choice" | "policy_reversal",
        "doc_a": doc,
        "doc_b": doc,
        "reason": str,
        "shared_topics": [str],
    }
    """
    # Filter to resolved debates only
    debates = [d for d in docs if d["type"] == "debate"
               and d.get("resolution") in ("ADOPT", "ADOPT_WITH_DISSENT")]

    contradictions = []

    for i, a in enumerate(debates):
        for b in debates[i + 1:]:
            result = _check_contradiction(a, b, min_overlap)
            if result:
                contradictions.append(result)

    return contradictions


def _check_contradiction(a, b, min_overlap):
    """Check if two debate docs contradict each other."""
    a_topics = set(a.get("topic_tokens", []))
    b_topics = set(b.get("topic_tokens", []))

    if not a_topics or not b_topics:
        return None

    # Topic overlap
    shared = a_topics & b_topics
    overlap = len(shared) / min(len(a_topics), len(b_topics)) if min(len(a_topics), len(b_topics)) > 0 else 0

    if overlap < min_overlap:
        return None

    shared_list = sorted(shared)[:5]

    # Check for antonym pairs in winning options
    a_winner_tokens = set(tokenize(a.get("winning_option", "") or ""))
    b_winner_tokens = set(tokenize(b.get("winning_option", "") or ""))

    for aw in a_winner_tokens:
        for bw in b_winner_tokens:
            if (aw, bw) in _ANTONYM_SET:
                return {
                    "type": "direct_opposite",
                    "doc_a": a,
                    "doc_b": b,
                    "reason": "Winner '%s' vs '%s' are antonyms (%s/%s)" % (
                        a.get("winning_option", ""), b.get("winning_option", ""), aw, bw),
                    "shared_topics": shared_list,
                }

    # Check for different winners on same topic (exclusive choice)
    a_winner = (a.get("winning_option") or "").lower().strip()
    b_winner = (b.get("winning_option") or "").lower().strip()

    if a_winner and b_winner and a_winner != b_winner and overlap > 0.5:
        return {
            "type": "exclusive_choice",
            "doc_a": a,
            "doc_b": b,
            "reason": "Same topic, different winners: '%s' vs '%s'" % (
                a.get("winning_option", ""), b.get("winning_option", "")),
            "shared_topics": shared_list,
        }

    # Check for policy reversal (same topic, one ADOPT one changed later)
    if overlap > 0.4 and a.get("timestamp") and b.get("timestamp"):
        if a["timestamp"] < b["timestamp"]:
            earlier, later = a, b
        else:
            earlier, later = b, a

        e_winner = (earlier.get("winning_option") or "").lower()
        l_winner = (later.get("winning_option") or "").lower()

        if e_winner and l_winner and e_winner != l_winner:
            return {
                "type": "policy_reversal",
                "doc_a": earlier,
                "doc_b": later,
                "reason": "Earlier chose '%s', later chose '%s'" % (
                    earlier.get("winning_option", ""), later.get("winning_option", "")),
                "shared_topics": shared_list,
            }

    return None

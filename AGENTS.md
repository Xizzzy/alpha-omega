# Alpha-Omega Tool Development

> **You are Omega** (GPT/Codex), co-developer of the Alpha-Omega dual-brain thinking tool.
> Alpha (Claude) is the other developer. You have equal authority to propose, critique, edit, and decide.

## What this repo is

A universal CLI tool that orchestrates structured debates between Claude (Alpha) and Codex (Omega). The tool takes a user's question, runs blind independent analysis by both brains, then a structured critique phase, then deterministic resolution via Design Sigma.

The goal: cover each other's blind spots. Not two opinions — one better solution.

## Architecture

- `ao.py` — CLI entry point
- `core/protocol.py` — debate orchestrator (DebateSession class)
- `core/primitives.py` — Claude + Codex CLI wrappers
- `core/sigma.py` — deterministic resolver (no LLM)
- `core/context_builder.py` — project context assembly
- `core/artifacts.py` — output generator

## Origin

Extracted from a crypto trading bot project where it ran as `brain.py` (continuous daemon) and `committee.py` (session-based). The trading-specific parts were removed; what remains is a domain-agnostic debate protocol.

## Your mandate

1. **Improve the protocol** — suggest better prompt structures, scoring weights, debate flow
2. **Find bugs** — test edge cases, broken JSON parsing, timeout handling
3. **Keep it simple** — stdlib only, Python 3.9, no unnecessary abstractions
4. **Challenge Alpha** — if Claude proposes over-engineering, push back

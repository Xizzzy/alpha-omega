# Alpha-Omega — Universal Dual-Brain Thinking Tool

## Overview

CLI tool that orchestrates structured debates between two genuinely different AI systems (Claude=Alpha, Codex=Omega). The core value: different neural networks have different blind spots, and the protocol between them surfaces what neither would see alone.

**Not two opinions. One solution where blind spots are already covered.**

## Architecture

```
ao.py                       Backward-compatible wrapper
pyproject.toml              Package metadata, `ao` entry point
alpha_omega/
  cli.py                    CLI commands (doctor, debate, init, history, status)
  primitives.py             Claude + Codex CLI wrappers (run_alpha, run_omega)
  protocol.py               Debate orchestrator (DebateSession) — the heart
  sigma.py                  Design Sigma — deterministic resolver, no LLM
  context_builder.py        Assembles project context for both brains
  artifacts.py              Generates markdown artifact pack + saves to project
```

## Protocol flow

1. **Context assembly** — reads CLAUDE.md, AGENTS.md, .alpha-omega/ from target project
2. **Blind memos** — Alpha and Omega independently analyze (neither sees the other)
3. **Cross-examination** — steelman first, then critique, then concessions
4. **Design Sigma** — deterministic scoring: evidence quality, feasibility, reversibility
5. **Artifact pack** — resolution + options + debate + assumptions + open questions

## Three invariants (ALL must hold)

1. **Different** — Claude and Codex are structurally different (training, weights, biases)
2. **Competent** — both frontier-class, neither is weaker
3. **Quality protocol** — Sigma scores evidence strength, not volume of objection

## Resolution states

- `ADOPT` — strong consensus
- `ADOPT_WITH_DISSENT` — winner with recorded minority concern
- `RUN_EXPERIMENT` — both plausible, need data
- `NEEDS_USER_CHOICE` — depends on user priorities, not logic
- `INSUFFICIENT_EVIDENCE` — neither brain had strong evidence
- `DEADLOCK` — fundamental disagreement

## Integration

- Global skill: `~/.claude/skills/alpha-omega/SKILL.md` — available in any Claude Code session
- Per-project memory: `.alpha-omega/` directory (decisions.md, debates/)
- Omega memory: `AGENTS.md` at project root (Codex reads automatically)

## Origin

Extracted from makemoney project (crypto trading bot) where it ran as brain.py daemon + committee.py sessions. Generalized to work for any domain.

## Development

- Python 3.9+ (no 3.10+ syntax)
- stdlib only (no pip dependencies)
- Install: `pip install -e .` (editable) or `pipx install .`
- Test: `ao debate "question"` or `python3 ao.py debate "question"`

## Self-development with AO

This project is bootstrapped: use Alpha-Omega debates for its own development.

When to run a debate before making changes:
- Architecture decisions (new modules, protocol changes, scoring weights)
- Non-trivial refactors that affect multiple files
- Adding new features to the protocol or Sigma
- Any change where the right approach isn't obvious

How to invoke:
```bash
ao debate "your question about the change"
ao debate --extra alpha_omega/sigma.py "should we change scoring weights?"
```

Check past decisions before starting new work:
```bash
ao history
```

## Rules

- NEVER hardcode project-specific paths — everything via --project or cwd
- Prompts must be domain-agnostic (no trading jargon in templates)
- Sigma must be deterministic (no LLM calls in resolution)
- Blind phase is sacred — never show Alpha's output to Omega before Omega commits

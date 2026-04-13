# Alpha-Omega

Dual-brain thinking tool. Two genuinely different AI systems (Claude + Codex) independently analyze a problem, then debate to find each other's blind spots.

**Not two opinions. One solution where blind spots are already covered.**

## Install

```bash
# Install with pipx (recommended)
pipx install alpha-omega

# Or with pip
pip install alpha-omega

# Or run directly from source
python3 ao.py <command>
```

## Quick start

```bash
# 1. Check prerequisites
ao doctor

# 2. Initialize AO in your project
cd your-project
ao init

# 3. Run a debate
ao debate "Should we use PostgreSQL or SQLite for this project?"

# 4. With extra context files
ao debate --extra schema.sql --extra requirements.txt "Design the data layer"

# 5. Different modes
ao debate --mode specify "Design the authentication subsystem"
ao debate --mode audit "Review the current API rate limiting"

# 6. Check history
ao history
ao status
```

## How it works

```
User Question
    |
    v
[Context Assembly]  -- reads CLAUDE.md, AGENTS.md, .alpha-omega/
    |
    +--------+--------+
    |                 |
    v                 v
 [Alpha]          [Omega]      <-- BLIND: neither sees the other's output
 Claude            Codex
 memo              memo
    |                 |
    +--------+--------+
    |                 |
    v                 v
 [Alpha]          [Omega]      <-- CRITIQUE: steelman first, then find blind spots
 critique          critique
    |                 |
    +--------+--------+
             |
             v
      [Design Sigma]            <-- DETERMINISTIC: scores argument quality, not volume
             |
             v
      [Artifact Pack]           <-- RESOLUTION + decisions + open questions
```

## Three invariants

1. **Different** — Claude and Codex have different training data, different weights, different blind spots
2. **Competent** — both are frontier-class models, not one strong + one weak
3. **Quality protocol** — Sigma evaluates evidence strength, not just agreement/disagreement

## Requirements

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (`claude` in PATH)
- [OpenAI Codex CLI](https://github.com/openai/codex) (`codex` in PATH)
- Python 3.9+

Run `ao doctor` to verify all prerequisites.

## Project structure

```
alpha-omega/
├── ao.py                  # Backward-compatible entry point
├── pyproject.toml         # Package metadata
├── alpha_omega/
│   ├── cli.py             # CLI commands (doctor, debate, init, ...)
│   ├── primitives.py      # Claude + Codex CLI wrappers
│   ├── protocol.py        # Debate orchestrator
│   ├── sigma.py           # Design Sigma resolver (deterministic, no LLM)
│   ├── context_builder.py # Project context assembly
│   └── artifacts.py       # Artifact pack generator

Your project/
├── .alpha-omega/          # AO memory (created by `ao init`)
│   ├── INDEX.md
│   ├── decisions.md       # Decision log
│   └── debates/           # Full transcripts
├── AGENTS.md              # Omega's persistent memory
└── CLAUDE.md              # Alpha's persistent memory
```

## Integration with Claude Code

Global skill installed at `~/.claude/skills/alpha-omega/SKILL.md`.
Use `/alpha-omega` from any Claude Code session.

# Alpha-Omega

Dual-brain thinking tool. Two genuinely different AI systems (Claude + Codex) independently analyze a problem, then debate to find each other's blind spots.

**Not two opinions. One solution where blind spots are already covered.**

## Quick start

```bash
# Initialize AO in your project
python3 ~/alpha-omega/ao.py init

# Run a debate
python3 ~/alpha-omega/ao.py debate "Should we use PostgreSQL or SQLite for this project?"

# With extra context files
python3 ~/alpha-omega/ao.py debate --extra schema.sql --extra requirements.txt "Design the data layer"

# Different modes
python3 ~/alpha-omega/ao.py debate --mode specify "Design the authentication subsystem"
python3 ~/alpha-omega/ao.py debate --mode audit "Review the current API rate limiting"
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

- [Claude Code CLI](https://claude.ai/code) (`claude` in PATH)
- [OpenAI Codex CLI](https://github.com/openai/codex) (`codex` in PATH)
- Python 3.9+

## Project structure

```
~/alpha-omega/
├── ao.py              # CLI entry point
├── core/
│   ├── primitives.py  # Claude + Codex CLI wrappers
│   ├── protocol.py    # Debate orchestrator
│   ├── sigma.py       # Design Sigma resolver
│   ├── context_builder.py  # Project context assembly
│   └── artifacts.py   # Artifact pack generator
└── templates/         # (future) init templates

Your project/
├── .alpha-omega/      # AO memory (created by `ao init`)
│   ├── INDEX.md
│   ├── decisions.md   # Decision log
│   └── debates/       # Full transcripts
└── AGENTS.md          # Omega's persistent memory
```

## Integration with Claude Code

Global skill installed at `~/.claude/skills/alpha-omega/SKILL.md`.
Use `/alpha-omega` from any Claude Code session.

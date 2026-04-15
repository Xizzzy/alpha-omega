# Alpha-Omega

Dual-brain thinking tool. Two genuinely different AI systems (Claude + Codex) independently analyze a problem, then debate to find each other's blind spots.

**Not two opinions. One solution where blind spots are already covered.**

## Install

```bash
pipx install alpha-omega    # recommended
pip install alpha-omega      # or with pip
```

## Quick start

```bash
ao setup                     # check prerequisites + initialize project
ao debate "your question"    # full dual-brain debate
```

## Commands

| Command | What it does |
|---------|-------------|
| `ao setup` | First-time setup: prerequisites + init + skill install |
| `ao doctor` | Check Claude CLI, Codex CLI, auth, project state |
| `ao debate "question"` | Full debate: blind memos → critique → Sigma resolution |
| `ao review` | Quick code review on unstaged changes |
| `ao review --staged` | Review staged changes |
| `ao review --branch main` | Review all changes since branch |
| `ao implement <id>` | Execute a debate resolution with either brain |
| `ao recall <query>` | Search past decisions and reviews |
| `ao contradictions` | Find conflicting past decisions |
| `ao init` | Create .alpha-omega/ in current project |
| `ao history` | Show recent debate outcomes |
| `ao status` | Show project AO state |

## How it works

```
    ┌──────────┐                              ┌──────────┐
    │  Alpha   │          BLIND PHASE         │  Omega   │
    │  Claude  │  ── independently analyze ── │  Codex   │
    └────┬─────┘                              └────┬─────┘
         │              CRITIQUE PHASE              │
         │  ── steelman + critique + concessions ── │
         └──────────────────┬───────────────────────┘
                            │
                   ┌────────▼────────┐
                   │  Design Sigma   │  ← deterministic, no LLM
                   │  (resolution)   │
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │  Artifact Pack  │  ← resolution + dissent + risks
                   └─────────────────┘
```

## Resolution states

| State | Meaning |
|-------|---------|
| `ADOPT` | Strong consensus |
| `ADOPT_WITH_DISSENT` | Winner with recorded minority concern |
| `RUN_EXPERIMENT` | Both plausible, need data |
| `NEEDS_USER_CHOICE` | Depends on user priorities |
| `INSUFFICIENT_EVIDENCE` | Both brains uncertain |
| `DEADLOCK` | Fundamental disagreement |

## Configuration

Per-project config in `.alpha-omega/config.json`:

```json
{
  "alpha_model": "claude-sonnet-4-5",
  "alpha_timeout": 300,
  "alpha_max_turns": 8,
  "omega_timeout": 600,
  "review_timeout": 180,
  "implement_timeout": 900,
  "implement_max_turns": 6
}
```

Per-brain timeouts are honored independently: Omega tends to run longer and gets 600s by default, Alpha gets 300s with up to 8 tool-use turns.

CLI flag precedence: `--alpha-timeout` / `--omega-timeout` (per-brain) > `--timeout` (shared override) > `.alpha-omega/config.json` > defaults.

## Requirements

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (`claude` in PATH)
- [OpenAI Codex CLI](https://github.com/openai/codex) (`codex` in PATH)
- Python 3.9+

Run `ao doctor` to verify all prerequisites.

## Project structure

```
Your project/
├── .alpha-omega/
│   ├── config.json      # Model and timeout settings
│   ├── decisions.md     # Decision log
│   ├── sessions/        # Structured JSON per debate
│   ├── debates/         # Full markdown transcripts
│   └── reviews/         # Review results
├── AGENTS.md            # Omega's project memory
└── CLAUDE.md            # Alpha's project memory
```

## Integration with Claude Code

`ao setup` installs a global skill. Use `/alpha-omega` from any Claude Code session.

## Philosophy

See [MANIFESTO.md](MANIFESTO.md) — on the necessary architecture of thought that cannot be monological.

## License

MIT

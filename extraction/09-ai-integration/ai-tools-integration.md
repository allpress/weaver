# AI Tools Integration

The tool is designed to be used by AI coding assistants as a first-class user. This document covers:

1. The CLAUDE.md contract.
2. Slash-command skills for Claude Code.
3. Project linking (registering directories with Claude Code + Copilot + Cursor).
4. Voice/personality system.

---

## 1. The CLAUDE.md Pattern

`CLAUDE.md` at the tool root is the **authoritative AI-assistant reference**. Every assistant that enters the tool's directory reads this file first.

### Structure

```markdown
# <tool> - one-line pitch

> Brief paragraph: what the tool is and why it exists.

## Mandatory AI Rules
(Rules that apply to every interaction — violating them causes real failures.)

## Quick Command Reference
(Table: command → purpose. Keep this tight — ~20 rows. Detail lives in docs/.)

## Detail Pages
(Links into docs/claude/ for deeper topics.)

## Context System (Overview)
(Enough to explain contexts in 10 lines. Link to architecture.md for details.)

## Installation (Quick Start)
(Two or three commands. Link to onboarding.md for the full walkthrough.)
```

### Mandatory AI Rules (examples)

The "Mandatory AI Rules" section is the most-read part by AI assistants. Rules we found valuable:

- **"Before any browser command, verify the CDP watcher is running. If not, stop and tell the user to start it. Never work around it."**
- **"Never use bare `ps` or `kill` — blocked by sandbox. Use `<tool> server ps` / `server kill`."**
- **"If a REST API call fails auth and you don't have a valid token in hand, STOP. Do not attempt to acquire tokens from inside the sandbox."**
- **"Playwright is for screen scraping only (last resort). Never use it when a REST API works."**
- **"Never instantiate Playwright in loops. Use REST clients for bulk operations."**
- **"Must NOT cache authenticated data to disk."**
- **"Always use: `git -c 'credential.helper=store --file=$(pwd)/.git-credentials' push origin <branch>`. Never bare `git push` — hangs waiting for keychain."**
- **"Tokens are environment-specific. Run `env <env>` BEFORE `auth login`."**

These are **behavioral contracts**, not style suggestions. Each rule corresponds to a class of past failures. Each has a **reason** inline so the assistant can judge edge cases.

### Layering

| File | Role |
|------|------|
| `CLAUDE.md` | Authoritative. Read first. Quick reference. Rules. |
| `docs/claude/commands.md` | Full command reference |
| `docs/claude/architecture.md` | Multi-context architecture |
| `docs/claude/auth-and-security.md` | Auth, Playwright policy, caching policy |
| `docs/claude/environment.md` | Git push workaround, certs, RAG setup |
| `docs/claude/onboarding.md` | Full setup walkthrough |
| `docs/claude/<provider-family>.md` | Per-provider detail pages (issues, logs, code, wiki) |
| `docs/claude/skills-reference.md` | Skills framework + list |
| `docs/claude/media-skills.md` | Video + audio |
| `docs/claude/graph-engine.md` | Graph build / analyze / export |
| `contexts/<name>/CLAUDE.md` | Per-context AI reference (repo inventory, domain terms) |

**Rule**: CLAUDE.md stays concise (< 300 lines). Detail pages are where depth lives. When CLAUDE.md needs to grow, spin out a new detail page and link to it.

---

## 2. Slash-Command Skills for Claude Code

Claude Code supports user-authored skills (`/skill-name`) defined as markdown files in `~/.claude/skills/`.

### Skill File Format

```markdown
---
name: my-skill
description: What this skill does (shown to user when they type /)
argument-hint: optional hint about expected args
---

# Skill body — instructions Claude follows when the skill is invoked.

## Step 1
Do this first.

## Step 2
Then this.
```

### Per-Context Skills

Each known context can ship its own slash-command skills under `_config/known_contexts/<ctx>/skills/<skill-name>/skill.md`. These get copied to `~/.claude/skills/<ctx>-<skill>/skill.md` on setup, so users invoke them as `/<ctx>-<skill>`.

Examples (generalized):
- `/myteam-architect` — answer architecture questions in the context's voice.
- `/myteam-spec-create` — scaffold a new design spec from an issue key.
- `/myteam-merge-request` — create an MR with the team's conventions.
- `/myteam-log-analyze` — investigate a bug across the team's services.

### Claude Skills Manager

CLI surface for managing these:

```
<tool> claude-skills list                    # available skills (shipped + per-context)
<tool> claude-skills installed               # what's in ~/.claude/skills/
<tool> claude-skills install [name]          # install all or named
<tool> claude-skills uninstall <name>
<tool> claude-skills sync                    # re-sync all contexts' skills
<tool> claude-skills status
```

Implementation: `scripts/claude_skills_manager.py`. Copies files (no symlinks — simpler, works cross-platform, avoids permission edge cases).

### Repo Post-Sync Hook: Generate Skills From Repos

The original had a hook (`scripts/repo_post_sync/specification_commands.py`) that scanned a docs-template repo after sync and regenerated a family of slash commands (`/spec-create`, `/spec-update`, `/spec-review`, `/spec-research`) so the Claude Code interface stays in sync with whatever is in the source repo.

Generalize this pattern: any post-sync hook can write to `.claude/commands/` or `~/.claude/skills/` to keep slash commands fresh. The hook decides its own naming convention.

---

## 3. Project Linking

Users typically want to use the tool from inside **other** projects, not only from its own directory.

### Two Approaches

**1. Symlink (legacy)**
```bash
ln -s /path/to/<tool> /path/to/project/_<tool>
```

Project's `CLAUDE.md` references `_<tool>/<tool>.py ...` commands. Cross-platform caveat: Windows needs `mklink /J` (junction) or Developer Mode for symlinks.

**2. Registry (preferred)**
```bash
<tool> link <project-path>              # register
<tool> link <project-path> --init       # register + write AI instruction files
<tool> link self                        # register the tool itself
<tool> link list
<tool> link remove <path>
<tool> link sync                        # re-sync registry to AI tool settings
```

This writes to:
- **Claude Code**: `~/.claude/settings.json` → `permissions.additionalDirectories`.
- **Copilot**: VS Code user settings → `github.copilot.chat.codeGeneration.instructions`.
- **Workspace**: generates a multi-folder `<tool>.code-workspace`.

The project's `CLAUDE.md` references the tool by absolute path via `<tool> ...` (no `_<tool>/` prefix needed because the tool is registered globally).

### `--init`: Bootstrap AI Instruction Files

When `--init` is passed, `link` adds an AI-integration section to:

- `<project>/CLAUDE.md` (appended or updated; never clobbers existing content).
- `<project>/.github/COPILOT_INSTRUCTIONS.md`.
- `<project>/LINCAI_INSTRUCTIONS.md` (or named after the tool) — universal fallback for other AI tools.

### INIT.md

The tool root ships an `INIT.md` that AI assistants read when the user says *"link this project to the tool"*. It describes the integration steps end-to-end so the assistant can perform them autonomously. See the `/LINCAI_INIT.md` in the source project for a reference template.

Key point: **INIT.md is written to be read by an AI**, not a human. It uses imperative, step-wise instructions; every step is self-contained; the assistant decides when to stop and ask.

---

## 4. Voice / Personality System

Optional. A voice file defines a persona the tool uses when the user addresses it by name. This is **purely a feature flag** and easy to disable or replace.

### Config

```ini
[personality]
use_voice = true
voice_file = voice/PRINCIPLED_VOICE.md
```

`voice/<VOICE>.md` is a markdown file describing the voice — tone, phrasing, what to avoid. Claude Code reads it when the user addresses the tool by name ("LincAi, tell me about...") and responds in-voice.

### Open-Source Default

Ship a **neutral default voice file**: polite, concise, honest, refuses to flatter, refuses to speculate without evidence. Users can drop in their own voice file (Gandalf, Socrates, a cartoon mascot, a corporate persona) without touching code.

```markdown
# DEFAULT VOICE — Neutral

When the user addresses the tool by name, respond:
- Concise (default ≤ 4 sentences unless the user asks for depth).
- Honest about uncertainty. If unsure, say so.
- Principled. Don't invent data, don't guess URLs, don't flatter.
- Helpful first, personality second.
```

### Invocation

The voice applies **only when the user addresses the tool directly** ("<tool>, ..."). Regular CLI invocations stay plain.

---

## 5. The Complete AI Contract

Putting it together, an AI assistant that enters the tool's directory:

1. Reads `CLAUDE.md` → gets mandatory rules + command overview.
2. Follows links into `docs/claude/*.md` when needed.
3. When the user invokes a slash command, runs the skill's instructions from `~/.claude/skills/<skill>/skill.md`.
4. When the user asks about another project that's linked, invokes `<tool>` commands against the registered path.
5. When the user addresses the tool by name, responds in-voice.
6. When a command fails, reads the error — if it's an authentication failure, does NOT try to auto-fix, instead tells the user which command to run.
7. Writes no new documentation files unless explicitly asked.
8. Avoids caching authenticated data.
9. Uses `<tool> server ps` / `server kill` instead of bare `ps`/`kill`.

This contract is what makes the tool usable inside locked-down AI harnesses — every potentially-sandbox-hostile operation has a tool-provided safe wrapper.

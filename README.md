# claude-obsidian-sync

Auto-sync for Claude Code ↔ Obsidian: turns your VS Code Claude Code conversations into
categorized, self-updating Obsidian notes — and lets Claude read them back as active memory.

## What it does

**Part 1 — Passive sync**
- Watches your Claude Code session transcripts (`~/.claude/projects/*/*.jsonl`)
- Extracts only the readable conversation text (skips internal "thinking", tool calls, and
  system noise)
- Auto-detects a topic category (Deep Learning, Machine Learning, Statistics, Code, Research,
  etc., with a `Personal_General` fallback for anything unrelated) based on keywords in the
  conversation
- Writes one Markdown note per conversation session into your Obsidian vault — and keeps
  **updating that same note** as the conversation continues, instead of creating duplicates
- Runs silently in the background via Windows Task Scheduler (no console window, no manual
  steps after setup)

**Part 2 — Active memory (optional)**
- Exposes the vault to Claude Code via an MCP filesystem server, sandboxed to that folder only
- A `CLAUDE.md` project instruction tells Claude to check your notes before answering
  questions on the topics above, so past conversations inform future answers automatically

## Quick start

```powershell
python claude_obsidian_sync.py          # one-shot sync
python claude_obsidian_sync.py --watch 60   # loop every 60s
```

Before running, edit `OBSIDIAN_VAULT` in `claude_obsidian_sync.py` to point at your own vault.

## Full setup guide

See [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) for:
- The architecture diagram
- 5 real bugs hit during setup and how they were fixed (schtasks path bugs, console windows
  killing the background process, duplicate notes, etc.)
- Step-by-step manual installation
- A ready-to-paste prompt to have an AI replicate this whole setup on another machine

## Requirements

- Windows 10/11
- Python 3.9+ (standard library only, no external dependencies)
- [Obsidian](https://obsidian.md)
- [Claude Code](https://claude.com/claude-code)

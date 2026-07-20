# Claude Code ↔ Obsidian Integration — Definitive Guide

This is the **verified, working version** of a two-part system:

1. **Passive sync** — automatically archives Claude Code (CLI/VS Code) conversations into
   categorized Obsidian notes.
2. **Active memory** — lets Claude Code read those same notes back via an MCP server, guided
   by a standing `CLAUDE.md` instruction, so it can use your past notes as context for future
   answers.

> This document reflects the final working state. It includes the real errors hit during
> setup and how they were fixed, so they don't get repeated.

---

## 1. Architecture diagram (final working version)

```
┌──────────────────────────────────────────────┐
│ YOU — VS Code + Claude Code                   │
│ You type: claude "explain transformers"       │
└────────────────────┬───────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ CLAUDE CODE                                    │
│ Saves the conversation live to:                │
│ ~/.claude/projects/<project>/<sessionId>.jsonl │
│ (NOT "transcripts/" — that folder doesn't exist)│
└────────────────────┬───────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐         PART 1: PASSIVE SYNC
│ WINDOWS TASK SCHEDULER                        │         (one-way: conversation → note)
│ Task: Claude_Code\Claude_Obsidian_Sync        │
│ Trigger: at Windows logon                     │
│ Runs: pythonw.exe (NO visible window)         │
│ claude_obsidian_sync.py --watch 60            │
└────────────────────┬───────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ PYTHON SCRIPT (every 60 seconds)              │
│ 1. Scans *.jsonl under ~/.claude/projects/*/   │
│ 2. Compares hash → did it change since last run?│
│ 3. If changed: parses ONLY readable text       │
│    (skips thinking, tool_use, system noise)    │
│ 4. Detects a topic category via keywords       │
│ 5. Writes/updates ONE note per session         │
│    (named by sessionId, never duplicated)      │
└────────────────────┬───────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ OBSIDIAN VAULT                                 │
│ D:\...\Master_AI\Obsidian\{Category}\          │
│ Readable note, tagged, self-updating           │
└────────────────────┬───────────────────────────┘
                     ↓ (read back)
┌──────────────────────────────────────────────┐         PART 2: ACTIVE MEMORY
│ MCP SERVER "obsidian"                          │         (two-way: note → informs answers)
│ @modelcontextprotocol/server-filesystem        │
│ Sandboxed to the Obsidian vault folder only    │
│ Exposes tools: read_file, search_files,        │
│ list_directory, write_file, etc.               │
└────────────────────┬───────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ CLAUDE.md (project root)                       │
│ Standing instruction: "before answering        │
│ master's-degree topics, check the vault first" │
│ Loaded automatically at the start of every     │
│ NEW Claude Code session in this project        │
└────────────────────┬───────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ NEXT CONVERSATION                              │
│ You ask: "what have I studied about CNNs?"     │
│ Claude checks the vault via MCP and answers     │
│ using your own past notes as context           │
└──────────────────────────────────────────────┘
```

---

## 2. The 5 real bugs that had to be fixed (Part 1 — sync)

If you replicate this on another PC (or have an AI do it), watch out for these:

| # | Symptom | Real cause | Fix |
|---|---|---|---|
| 1 | Script said "transcripts folder not found" | Claude Code does **not** save to `~/.claude/transcripts/`. That folder doesn't exist by default. | Real transcripts live at `~/.claude/projects/<project-folder>/<sessionId>.jsonl` |
| 2 | Notes were created named like `pid_12924_sessionId_...` with no real content | The script (design mistake) was also reading `~/.claude/sessions/*.json`, which only holds metadata (pid, sessionId), not conversation text | That source was removed; only `projects/*/*.jsonl` is read now |
| 3 | `schtasks /create` with `/tr` failed with "cannot find the file specified" even though the path existed | The project folder name had **many consecutive spaces** (`!           CLAUDE`), and `schtasks.exe` collapses those spaces when storing the path, regardless of quoting | Use Windows' **8.3 short path** (no spaces): `(New-Object -ComObject Scripting.FileSystemObject).GetFile($path).ShortPath` → something like `D:\!CLAUD~1\...` |
| 4 | The task kept "dying" with exit code `-1073741510` | It used `python.exe` (which opens a visible console). If that window gets closed (even by accident), the process dies | Use **`pythonw.exe`** instead of `python.exe` — runs with no window at all, can't be closed by accident |
| 5 | Every 60s it seemed to create a new note for the same conversation | The note filename was generated with a fresh timestamp each run | The note filename is now the **sessionId** (stable); if it already exists, it gets **overwritten/updated** instead of creating a new one |

---

## 3. Final folder structure

```
D:\...\Master_AI\
├── claude_obsidian_sync.py     ← sync script (Part 1, full code below)
└── Obsidian/                   ← Obsidian vault (also the MCP server's sandbox root)
    ├── Deep_Learning/
    ├── Machine_Learning/
    ├── Statistics/
    ├── AI_Fundamentals/
    ├── Research_Notes/
    ├── Code_Analysis/
    └── Personal_General/       ← fallback for anything unrelated to the topics above

<project root>\
└── CLAUDE.md                   ← standing instruction (Part 2, full content below)

~/.claude.json                  ← holds the "obsidian" MCP server entry (Part 2)
```

---

## 4. Full script code — Part 1: sync (final, corrected version)

Save this as `claude_obsidian_sync.py` inside your project folder:

```python
"""
Syncs Claude Code conversations -> Obsidian automatically.
Reads the .jsonl files under ~/.claude/projects/<project>/ (Claude Code's
real transcripts) and generates one readable Markdown note per conversation.
"""
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

# Configuration — ADJUST THIS PATH to your Obsidian vault
CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
OBSIDIAN_VAULT = Path(r"D:\PATH\TO\YOUR\VAULT\Obsidian")
SYNC_STATE_FILE = Path.home() / ".claude" / "obsidian_sync_state.json"
CATEGORY_MAPPING = {
    "deep learning": "Deep_Learning",
    "neural network": "Deep_Learning",
    "cnn": "Deep_Learning",
    "transformer": "Deep_Learning",
    "machine learning": "Machine_Learning",
    "classification": "Machine_Learning",
    "regression": "Machine_Learning",
    "statistic": "Statistics",
    "probability": "Statistics",
    "distribution": "Statistics",
    "code": "Code_Analysis",
    "script": "Code_Analysis",
    "function": "Code_Analysis",
    "research": "Research_Notes",
    "paper": "Research_Notes",
    "thesis": "Research_Notes",
}
DEFAULT_CATEGORY = "Personal_General"  # anything unrelated to the topics above


def load_sync_state() -> dict:
    if SYNC_STATE_FILE.exists():
        with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": {}}


def save_sync_state(state: dict):
    with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_file_hash(filepath: Path) -> str:
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def detect_category(text: str) -> str:
    text_lower = text.lower()
    for keyword, category in CATEGORY_MAPPING.items():
        if keyword in text_lower:
            return category
    return DEFAULT_CATEGORY


def extract_text_blocks(message: dict) -> list[str]:
    """Extracts only the readable text blocks of a message (ignores thinking/tool_use/tool_result)."""
    content = message.get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "").strip()
            if text:
                texts.append(text)
    return texts


def parse_jsonl_conversation(jsonl_path: Path) -> list[tuple[str, str]]:
    """Returns a list of (role, text) readable turns from a .jsonl transcript."""
    turns = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = obj.get("type")
            if entry_type not in ("user", "assistant"):
                continue  # skip queue-operation, system attachments, etc.

            message = obj.get("message")
            if not isinstance(message, dict):
                continue

            for text in extract_text_blocks(message):
                role = "User" if entry_type == "user" else "Claude"
                turns.append((role, text))

    return turns


def build_note_markdown(session_id: str, turns: list[tuple[str, str]], category: str, created: str) -> str:
    first_user_text = next((t for role, t in turns if role == "User"), "Claude Code conversation")
    title = first_user_text.strip().splitlines()[0][:80]

    body_parts = [f"### {role}\n\n{text}\n" for role, text in turns]

    return f"""# {title}

**Source:** Claude Code
**Session:** `{session_id}`
**Last updated:** {created}
**Category:** `{category}`

---

## Conversation

{"\n---\n\n".join(body_parts)}

---

## Tags
#{category.lower()} #claude-code #auto-sync

## Related links
- [[{category.replace('_', ' ')}]]
"""


def sync_note_for_session(jsonl_path: Path, state: dict) -> Optional[Path]:
    session_id = jsonl_path.stem
    turns = parse_jsonl_conversation(jsonl_path)

    if not turns:
        return None  # no readable content (e.g. only queue-operations)

    full_text = "\n".join(t for _, t in turns)
    category = detect_category(full_text)

    note_paths = state.setdefault("note_paths", {})

    # If this session already had a note, reuse the same path (avoids duplicates)
    existing = note_paths.get(session_id)
    if existing and Path(existing).exists():
        note_path = Path(existing)
    else:
        category_path = OBSIDIAN_VAULT / category
        category_path.mkdir(parents=True, exist_ok=True)
        note_path = category_path / f"{session_id}.md"
        note_paths[session_id] = str(note_path)

    note_content = build_note_markdown(
        session_id, turns, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note_content)

    return note_path


def sync_transcripts():
    """Walks every Claude Code project and syncs its conversations to Obsidian."""
    if not CLAUDE_PROJECTS_ROOT.exists():
        print(f"WARNING: Claude projects folder not found: {CLAUDE_PROJECTS_ROOT}")
        return

    state = load_sync_state()
    processed = state.setdefault("processed", {})

    jsonl_files = list(CLAUDE_PROJECTS_ROOT.glob("*/*.jsonl"))
    if not jsonl_files:
        print(f"WARNING: No transcripts (.jsonl) found under {CLAUDE_PROJECTS_ROOT}")
        return

    synced = 0
    for jsonl_path in jsonl_files:
        key = str(jsonl_path)
        file_hash = get_file_hash(jsonl_path)

        if processed.get(key) == file_hash:
            continue  # no changes since last sync

        try:
            note_path = sync_note_for_session(jsonl_path, state)
            if note_path:
                print(f"Note updated: {note_path}")
                synced += 1
            processed[key] = file_hash
        except Exception as e:
            print(f"ERROR processing {jsonl_path.name}: {e}")

    if synced > 0:
        save_sync_state(state)
        print(f"\nSync complete: {synced} note(s) updated")
    else:
        print("No changes")


def watch_mode(interval: int = 30):
    print(f"Watching {CLAUDE_PROJECTS_ROOT} every {interval}s...")
    print("(Press Ctrl+C to stop)")
    try:
        while True:
            sync_transcripts()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        watch_mode(interval)
    else:
        sync_transcripts()
```

> **Note:** if your conversations are in a language other than English, add the equivalent
> keywords to `CATEGORY_MAPPING` (e.g. Spanish `"código"`/`"codigo"` alongside `"code"`), or
> the category detection will default everything to `Research_Notes`.

---

## 5. Manual step-by-step installation — Part 1: sync

### Step 1 — Create the Obsidian folder structure

```powershell
$vault = "D:\PATH\TO\YOUR\PROJECT\Obsidian"
@("Deep_Learning","Machine_Learning","Statistics","AI_Fundamentals","Research_Notes","Code_Analysis") |
    ForEach-Object { New-Item -ItemType Directory -Path "$vault\$_" -Force }
```

### Step 2 — Save the script

Save the code from section 4 as `claude_obsidian_sync.py`, and **edit the line**:
```python
OBSIDIAN_VAULT = Path(r"D:\PATH\TO\YOUR\VAULT\Obsidian")
```
with your real path.

### Step 3 — Test the script manually first

```powershell
& "C:\Path\to\your\python.exe" claude_obsidian_sync.py
```

You should see `Note updated: ...` if you already have prior Claude Code conversations.
If it says "no transcripts found", check that `~/.claude/projects/` exists with
subfolders containing `.jsonl` files.

### Step 4 — Get short paths (no spaces) — avoids the schtasks bug

**Only needed if your project path has spaces in a folder name** (like `!           CLAUDE`):

```powershell
$fso = New-Object -ComObject Scripting.FileSystemObject
$shortPythonw = $fso.GetFile("C:\Path\to\your\pythonw.exe").ShortPath
$shortScript  = $fso.GetFile("C:\Path\to\your\claude_obsidian_sync.py").ShortPath
Write-Host "$shortPythonw"
Write-Host "$shortScript"
```

If your path has no spaces, you can just use the normal paths.

### Step 5 — Register the task in Windows Task Scheduler (as Administrator)

**Important:** use `pythonw.exe`, NOT `python.exe` (avoids the console window that can be
closed by accident and kill the process).

```powershell
schtasks /create /tn "Claude_Code\Claude_Obsidian_Sync" /tr "<SHORT_PYTHONW_PATH> <SHORT_SCRIPT_PATH> --watch 60" /sc onlogon /ru "<YOUR_USERNAME>" /f
```

### Step 6 — Verify it ran without errors

```powershell
schtasks /run /tn "Claude_Code\Claude_Obsidian_Sync"
Start-Sleep -Seconds 3
schtasks /query /tn "Claude_Code\Claude_Obsidian_Sync" /fo list /v | Select-String "Last Result"
Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object Id, StartTime
```

- `Last Result: 267009` → correct, the task is still running (it's a `--watch` script, it never "finishes")
- At least one `pythonw` process should show up with an `Id`

### Step 7 — Open Obsidian

Open Obsidian → "Open folder as vault" → select the `Obsidian` folder from Step 1.

---

## 6. Manual step-by-step installation — Part 2: active memory (MCP + CLAUDE.md)

This part turns the one-way archive into something Claude Code can actively read back and
use as context in future conversations.

### Step 1 — Install Node.js (required by the MCP server)

```powershell
winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
```

Restart your terminal/PowerShell session afterward so `node`/`npx` are on PATH.

### Step 2 — Test the filesystem MCP server manually once

```powershell
npx -y "@modelcontextprotocol/server-filesystem" "D:\PATH\TO\YOUR\VAULT\Obsidian"
```

You should see `Secure MCP Filesystem Server running on stdio` (a harmless `npm warn
deprecated` line is fine). Stop it with Ctrl+C — this was just a smoke test.

### Step 3 — Register the MCP server for your project

Two ways to do this, depending on what's available:

**A) If the `claude` CLI is on your PATH:**
```bash
claude mcp add obsidian -- npx -y @modelcontextprotocol/server-filesystem "D:\PATH\TO\YOUR\VAULT\Obsidian"
```

**B) If you're using the VS Code extension and `claude` is NOT on PATH** (this was the case
here): edit `~/.claude.json` directly. Find your project's entry under the top-level
`"projects"` key (it's keyed by the project's folder path) and set its `mcpServers`:

```json
"projects": {
  "D:/path/to/your/project": {
    "mcpServers": {
      "obsidian": {
        "type": "stdio",
        "command": "npx",
        "args": [
          "-y",
          "@modelcontextprotocol/server-filesystem",
          "D:\\PATH\\TO\\YOUR\\VAULT\\Obsidian"
        ]
      }
    }
  }
}
```

Validate the JSON is still well-formed after editing (e.g. `Get-Content ~/.claude.json -Raw
| ConvertFrom-Json` in PowerShell) before trusting it.

### Step 4 — Add a standing instruction in `CLAUDE.md`

Create (or edit) `CLAUDE.md` in your project root:

```markdown
# Project instructions

## Obsidian vault (study memory)

There is an MCP server called **"obsidian"** (filesystem, sandboxed to
`D:\PATH\TO\YOUR\VAULT\Obsidian`) containing notes auto-generated from past Claude Code
conversations, organized by category (Deep_Learning, Machine_Learning, Statistics,
AI_Fundamentals, Research_Notes, Code_Analysis).

**Before answering questions related to these topics**, check that vault first using the
"obsidian" MCP tools to see if relevant notes already exist. If there's relevant content,
mention/reuse it as context before answering from scratch. If the vault has nothing
relevant, just answer normally — no need to mention that you checked and found nothing.
```

### Step 5 — Open a brand-new Claude Code session to load the changes

Both the MCP config and `CLAUDE.md` are only read **at the start of a session**. A session
that was already running before you made these changes will NOT pick them up — open a new
one (in VS Code: new Claude Code chat / new session command).

### Step 6 — Test it

In the new session, ask something that should trigger a vault lookup, without mentioning
Obsidian or MCP explicitly:

```
What have I studied about convolutional neural networks?
```

If it works, Claude will use the "obsidian" MCP tools to read your notes and answer using
that context.

---

## 7. Ready-to-paste prompt for Claude Code (to replicate the whole system on another PC)

Copy and paste this as-is inside Claude Code (VS Code or terminal), and the AI will run
through the whole process (sync + active memory) adapted to that machine:

```
I want you to set up a two-part system on this Windows PC:

PART 1 — Passive sync: automatically archive my Claude Code conversations into an Obsidian
vault, with no manual steps needed after setup.

PART 2 — Active memory: let you (Claude Code) read that same vault back via an MCP server,
guided by a standing project instruction, so you use my past notes as context in future
conversations, without me having to ask for it explicitly every time.

Requirements for Part 1:

1. Claude Code's real transcripts live at `~/.claude/projects/<project>/<sessionId>.jsonl`
   (NOT a "transcripts/" folder — that doesn't exist). Each line is a JSON object; only
   entries with "type":"user" or "type":"assistant" matter, reading the blocks inside
   "message.content" where "type":"text" (skip "thinking", "tool_use", "tool_result", any
   line with "type":"queue-operation", or any line with a top-level "attachment" key —
   those are internal noise).

2. Create a Python script (no external dependencies) that:
   - Walks every .jsonl under ~/.claude/projects/*/
   - Detects changes by comparing an MD5 hash of the file against the last synced value
     (persist that state in a JSON file, e.g. ~/.claude/obsidian_sync_state.json)
   - Parses only the readable text (User/Claude) as described above
   - Detects a topic category via keywords in the text (deep learning, machine learning,
     statistics, code, etc. — ask me what categories I want if I haven't given you any, and
     include keywords in whatever language(s) I actually write in, not just English)
   - Creates one folder per category inside my Obsidian vault
   - Creates/updates ONE Markdown note per conversation session, using the sessionId (the
     .jsonl filename without extension) as a STABLE filename — if the session already has a
     note, it must overwrite/update it, never create a new duplicate note
   - Has a `--watch <seconds>` mode that loops the sync forever

3. Register it in Windows Task Scheduler to run automatically at logon, in the background,
   with NO visible console window (use pythonw.exe, not python.exe — a visible console can
   be closed by accident and would kill the process).

4. BEFORE registering the task, check whether any of the involved paths (Python, the script,
   the project folder) contain multiple consecutive spaces in a folder name. If so, use
   Windows' 8.3 short path for that specific path (get it with
   `(New-Object -ComObject Scripting.FileSystemObject).GetFile($path).ShortPath` in
   PowerShell) before passing it to `schtasks /create /tr`, because schtasks collapses/
   breaks paths with many consecutive spaces even when quoted.

5. After creating the task, trigger it manually with `schtasks /run`, wait a few seconds,
   and verify with `schtasks /query ... /fo list /v` that the last result is 0 or 267009
   (the "task is running" code), and confirm with Get-Process that the pythonw process exists.

6. Test it end-to-end: run the script once manually first (without --watch) against my
   existing real conversations, and show me the content of a generated note so I can
   confirm the text is readable (not raw JSON or metadata) before leaving it on autopilot.

Requirements for Part 2:

7. Check whether Node.js is installed (`node --version`). If not, ask me before installing it
   (e.g. via `winget install OpenJS.NodeJS.LTS`).

8. Add an MCP server named "obsidian" using `@modelcontextprotocol/server-filesystem`,
   sandboxed to the Obsidian vault folder from Part 1. Check whether the `claude` CLI is on
   PATH — if it is, use `claude mcp add`; if not (e.g. this is the VS Code extension without
   the CLI on PATH), edit `~/.claude.json` directly under this project's entry in the
   top-level "projects" key, and validate the JSON is still well-formed afterward.

9. Create/update a `CLAUDE.md` file in the project root with a standing instruction telling
   you to check the "obsidian" MCP vault before answering questions related to the
   categories from Part 1, and to just answer normally (without mentioning the check) if the
   vault has nothing relevant.

10. Remind me that both the MCP config and CLAUDE.md only take effect in a NEW session —
    the current one won't pick them up — and tell me exactly how to start a new session.

Go through each step and show me the results of each check before moving to the next one.
```

---

## 8. How to tell it's working (day to day)

**Part 1 (sync):**
- You don't run anything manually. Just use Claude Code normally.
- Each conversation (session) maps to one note that keeps getting updated.
- Wait up to 60 seconds after writing something before it shows up/updates in Obsidian (you
  may need to hit F5 in Obsidian to refresh the view).
- If you restart the PC, the task starts itself at logon — nothing to redo.

**Part 2 (memory):**
- Works automatically in every **new** session started after the setup — you don't need to
  mention Obsidian or MCP in your prompt.
- It's a judgment call by the model, guided by `CLAUDE.md` — expect it to check the vault
  reliably for clearly personal/study questions ("what have I studied about X"), and less
  reliably for generic-knowledge questions ("explain X") unless you ask it to check first.

## 9. Quick troubleshooting

| Problem | Diagnostic command |
|---|---|
| Not sure if sync is running | `Get-Process pythonw -ErrorAction SilentlyContinue` |
| Not sure if the task is registered correctly | `schtasks /query /tn "Claude_Code\Claude_Obsidian_Sync" /fo list /v` |
| Want to force a sync right now | `schtasks /run /tn "Claude_Code\Claude_Obsidian_Sync"` |
| Want to see the log of a manual sync run | `& "<python.exe>" claude_obsidian_sync.py` (without `--watch`, runs once and prints details) |
| Notes have no readable content | Make sure you're reading `~/.claude/projects/*/*.jsonl`, not `sessions/*.json` (that's just metadata) |
| MCP server doesn't seem to be used | Confirm you're in a session started *after* the `~/.claude.json`/`CLAUDE.md` edits — old sessions won't see them |
| `npx` fails / MCP won't start | Confirm Node.js is installed: `node --version` / `npx --version` |

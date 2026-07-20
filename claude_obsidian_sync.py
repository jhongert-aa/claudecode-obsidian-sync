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

# Configuration
CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
OBSIDIAN_VAULT = Path(r"D:\!           CLAUDE\Master_AI\Obsidian")
SYNC_STATE_FILE = Path.home() / ".claude" / "obsidian_sync_state.json"
CATEGORY_MAPPING = {
    "deep learning": "Deep_Learning",
    "neural network": "Deep_Learning",
    "red neuronal": "Deep_Learning",
    "cnn": "Deep_Learning",
    "transformer": "Deep_Learning",
    "machine learning": "Machine_Learning",
    "classification": "Machine_Learning",
    "clasificaci": "Machine_Learning",  # matches "clasificación"/"clasificacion"
    "regression": "Machine_Learning",
    "regresi": "Machine_Learning",  # matches "regresión"/"regresion"
    "statistic": "Statistics",
    "estad": "Statistics",  # matches "estadística"/"estadistica"
    "probabilit": "Statistics",
    "probabilidad": "Statistics",
    "distribution": "Statistics",
    "distribuci": "Statistics",  # matches "distribución"/"distribucion"
    "code": "Code_Analysis",
    "código": "Code_Analysis",
    "codigo": "Code_Analysis",
    "script": "Code_Analysis",
    "function": "Code_Analysis",
    "función": "Code_Analysis",
    "funcion": "Code_Analysis",
    "research": "Research_Notes",
    "investigaci": "Research_Notes",  # matches "investigación"/"investigacion"
    "paper": "Research_Notes",
    "tesis": "Research_Notes",
    "thesis": "Research_Notes",
}
DEFAULT_CATEGORY = "Personal_General"  # anything unrelated to the master's topics above


def load_sync_state() -> dict:
    """Loads which transcripts have already been processed."""
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

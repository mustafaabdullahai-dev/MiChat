"""Disk persistence for conversations.

Chats live as one JSON file per conversation under ``data/chats`` so a browser
refresh, a tab close or a server restart never loses history. Session state
stays the working cache; every mutation is written through to disk.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MICHAT_DATA_DIR", PROJECT_DIR / "data"))
CHATS_DIR = DATA_DIR / "chats"


def _ensure_dir() -> None:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)


def _path(chat_id: str) -> Path:
    safe = "".join(c for c in str(chat_id) if c.isalnum() or c in "-_")
    return CHATS_DIR / f"{safe or 'chat'}.json"


def load_chats() -> dict[str, dict]:
    """Read every stored chat. Unreadable files are skipped, not fatal."""
    if not CHATS_DIR.exists():
        return {}
    chats: dict[str, dict] = {}
    for file in sorted(CHATS_DIR.glob("*.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cid = payload.get("id") or file.stem
        chats[cid] = {
            "title": payload.get("title") or "New chat",
            "created": payload.get("created") or 0.0,
            "updated": payload.get("updated") or 0.0,
            "messages": payload.get("messages") or [],
        }
    return chats


def save_chat(chat_id: str, chat: dict) -> None:
    """Write one chat atomically (temp file + replace)."""
    try:
        _ensure_dir()
        payload = {
            "id": chat_id,
            "title": chat.get("title", "New chat"),
            "created": chat.get("created", 0.0),
            "updated": chat.get("updated", 0.0),
            "messages": chat.get("messages", []),
        }
        target = _path(chat_id)
        fd, tmp = tempfile.mkstemp(dir=str(CHATS_DIR), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except OSError:
        pass  # persistence is best-effort; never break the chat over it


def delete_chat_file(chat_id: str) -> None:
    try:
        _path(chat_id).unlink(missing_ok=True)
    except OSError:
        pass


def storage_summary() -> str:
    if not CHATS_DIR.exists():
        return "no saved chats"
    files = list(CHATS_DIR.glob("*.json"))
    return f"{len(files)} chat{'s' if len(files) != 1 else ''} saved"
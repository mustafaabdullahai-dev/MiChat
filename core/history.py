"""Conversation storage: grouped chat history + message rendering helpers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import streamlit as st

from .storage import delete_chat_file, load_chats, save_chat

CHATS_KEY = "chats"
ACTIVE_KEY = "active_chat"

SUGGESTIONS = [
    "Explain LangChain",
    "Write a Python function",
    "Build a FastAPI endpoint",
    "Explain RAG",
]

GROUP_ORDER = ["Today", "Yesterday", "Previous 7 Days", "Previous 30 Days", "Older"]


def init_history() -> None:
    """Hydrate session state from disk once per browser session."""
    if CHATS_KEY not in st.session_state:
        st.session_state[CHATS_KEY] = load_chats()
    if st.session_state.get(ACTIVE_KEY) not in st.session_state[CHATS_KEY]:
        st.session_state[ACTIVE_KEY] = None


def _persist(chat_id: str) -> None:
    chat = st.session_state.get(CHATS_KEY, {}).get(chat_id)
    if chat is not None:
        save_chat(chat_id, chat)


def _now() -> str:
    return datetime.now().strftime("%H:%M")


def get_active_id() -> str | None:
    return st.session_state.get(ACTIVE_KEY)


def get_history() -> list[dict]:
    cid = get_active_id()
    chats = st.session_state.get(CHATS_KEY, {})
    if cid in chats:
        return chats[cid]["messages"]
    return []


def add_message(role: str, content: str, meta: dict | None = None) -> None:
    chats = st.session_state.setdefault(CHATS_KEY, {})
    cid = get_active_id()
    if cid not in chats:
        cid = datetime.now().strftime("%Y%m%d%H%M%S%f")
        title = content.strip()[:40] + ("…" if len(content.strip()) > 40 else "")
        now = time.time()
        chats[cid] = {
            "title": title if role == "user" else "New chat",
            "messages": [],
            "created": now,
            "updated": now,
        }
        st.session_state[ACTIVE_KEY] = cid
    chat = chats[cid]
    chat["messages"].append(
        {"role": role, "content": content, "time": _now(), "meta": meta or {}}
    )
    chat["updated"] = time.time()
    _persist(cid)


def truncate_from(index: int) -> None:
    """Drop the message at ``index`` and everything after it."""
    cid = get_active_id()
    chat = st.session_state.get(CHATS_KEY, {}).get(cid)
    if chat:
        del chat["messages"][index:]
        chat["updated"] = time.time()
        _persist(cid)


def branch_from(index: int) -> str | None:
    """Fork the conversation into a new chat ending at ``index``."""
    chats = st.session_state.setdefault(CHATS_KEY, {})
    source = chats.get(get_active_id())
    if not source:
        return None
    messages = [dict(m) for m in source["messages"][: index + 1]]
    if not messages:
        return None
    now = time.time()
    cid = datetime.now().strftime("%Y%m%d%H%M%S%f")
    seed = next((m["content"] for m in messages if m["role"] == "user"), "New chat")
    chats[cid] = {
        "title": seed.strip()[:40] + ("…" if len(seed.strip()) > 40 else ""),
        "messages": messages,
        "created": now,
        "updated": now,
    }
    st.session_state[ACTIVE_KEY] = cid
    save_chat(cid, chats[cid])
    return cid


def new_chat() -> None:
    st.session_state[ACTIVE_KEY] = None


def switch_chat(chat_id: str) -> None:
    if chat_id in st.session_state.get(CHATS_KEY, {}):
        st.session_state[ACTIVE_KEY] = chat_id


def rename_active_chat(title: str) -> None:
    cid = get_active_id()
    chat = st.session_state.get(CHATS_KEY, {}).get(cid)
    if chat and title.strip():
        chat["title"] = title.strip()[:60]
        chat["updated"] = time.time()
        _persist(cid)


def delete_active_chat() -> None:
    cid = get_active_id()
    st.session_state.get(CHATS_KEY, {}).pop(cid, None)
    st.session_state[ACTIVE_KEY] = None
    if cid:
        delete_chat_file(cid)


def reset_history() -> None:
    delete_active_chat()


def list_chats() -> list[tuple[str, dict]]:
    chats = st.session_state.get(CHATS_KEY, {})
    return sorted(chats.items(), key=lambda kv: kv[1]["updated"], reverse=True)


def group_chats() -> list[tuple[str, list[tuple[str, dict]]]]:
    """Group chats into Today / Yesterday / Previous 7/30 Days / Older."""
    now = datetime.now()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    bounds = {
        "Today": start_today,
        "Yesterday": start_today - timedelta(days=1),
        "Previous 7 Days": start_today - timedelta(days=7),
        "Previous 30 Days": start_today - timedelta(days=30),
        "Older": datetime.min,
    }
    buckets: dict[str, list[tuple[str, dict]]] = {k: [] for k in GROUP_ORDER}
    for chat_id, meta in list_chats():
        ts = meta.get("created") or meta.get("updated") or time.time()
        dt = datetime.fromtimestamp(ts)
        for label in GROUP_ORDER:
            if dt >= bounds[label]:
                buckets[label].append((chat_id, meta))
                break
    return [(label, buckets[label]) for label in GROUP_ORDER if buckets[label]]


def export_markdown() -> str:
    lines = ["# Conversation Export\n"]
    for msg in get_history():
        label = "**You**" if msg["role"] == "user" else "**Assistant**"
        lines.append(f"{label} ({msg.get('time', '')}):\n\n{msg['content']}\n")
    return "\n".join(lines)


def export_json() -> str:
    return json.dumps(get_history(), ensure_ascii=False, indent=2)


def drop_last_assistant() -> None:
    cid = get_active_id()
    chat = st.session_state.get(CHATS_KEY, {}).get(cid)
    if chat and chat["messages"] and chat["messages"][-1]["role"] == "assistant":
        chat["messages"].pop()
        _persist(cid)


def last_user_text() -> str:
    for msg in reversed(get_history()):
        if msg["role"] == "user":
            return msg["content"]
    return ""


def meta_line(meta: dict) -> str:
    """Human readable stats for an assistant turn (tokens / duration)."""
    bits: list[str] = []
    if meta.get("tokens"):
        bits.append(f"≈{meta['tokens']} tokens")
    if meta.get("seconds"):
        bits.append(f"{meta['seconds']:.1f}s")
    if meta.get("model"):
        bits.append(str(meta["model"]))
    return " · ".join(bits)


def render_message(role: str, content: str, time_label: str = "", meta: dict | None = None) -> None:
    avatar = "🧑" if role == "user" else "⚡"
    marker = "lc-marker-user" if role == "user" else "lc-marker-bot"
    label = "USER" if role == "user" else "AI"
    with st.chat_message(role, avatar=avatar):
        st.markdown(
            f'<span class="lc-marker {marker}"></span>'
            f'<div class="lc-msg-label">{label}'
            f'<span class="lc-msg-time">{time_label}</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(content)
        if role == "assistant" and meta:
            line = meta_line(meta)
            if line:
                st.markdown(f'<div class="lc-msg-meta">{line}</div>', unsafe_allow_html=True)


def render_history() -> None:
    for msg in get_history():
        render_message(msg["role"], msg["content"], msg.get("time", ""), msg.get("meta"))

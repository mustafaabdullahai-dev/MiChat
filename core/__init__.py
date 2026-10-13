"""Shared configuration, prompt/chain builders, history helpers and UI."""

from .chains import build_chain, get_groq_llm, get_ollama_llm
from .config import GROQ_MODELS, load_css, resolve_api_key
from .history import add_message, init_history, render_history, render_message, reset_history
from .ui import run_chat_app

__all__ = [
    "GROQ_MODELS",
    "add_message",
    "build_chain",
    "get_groq_llm",
    "get_ollama_llm",
    "init_history",
    "load_css",
    "render_history",
    "render_message",
    "reset_history",
    "resolve_api_key",
    "run_chat_app",
]

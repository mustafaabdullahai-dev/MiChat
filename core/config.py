"""Configuration: secrets resolution, model catalog and static assets."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent.parent
STYLES_DIR = PROJECT_DIR / "styles"

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Respond directly without thinking steps "
    "or showing internal reasoning."
)

BRAND = {
    "name": "MiChat",
    "logo": "◈",
    "tagline": "AI Assistant",
}

# Layout metrics (px) — single source of truth for the CSS below.
SIDEBAR_WIDTH = 300
CONTENT_WIDTH = 1000
BLOCK_GUTTER = 80  # Streamlit block padding on each side

GROQ_MODELS = {
    "Qwen3.8 27B (fast)": "qwen/qwen3.8-27b",
    "GPT-OSS 120B (reasoning)": "openai/gpt-oss-120b",
    "GPT-OSS 20B (light)": "openai/gpt-oss-20b",
    "Allam 2 7B (Arabic-first)": "allam-2-7b",
}

OLLAMA_MODELS = ["llama2", "llama3.2", "llama3.1", "mistral", "gemma2"]


def _secret(name: str) -> str | None:
    """Read a value from Streamlit Secrets if a secrets file is configured."""
    try:
        import streamlit as st

        return st.secrets.get(name)  # type: ignore[no-any-return]
    except Exception:
        return None


def resolve_api_key(name: str = "GROQ_API_KEY") -> str | None:
    """Resolve an API key: Streamlit Secrets (cloud) first, then env/.env."""
    value = _secret(name) or os.getenv(name)
    if value:
        os.environ.setdefault(name, value)
        return value
    return None


def apply_tracing() -> None:
    """Enable LangSmith tracing only when a tracing key is present."""
    if resolve_api_key("LANGCHAIN_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")


def layout_css() -> str:
    """Column widths shared by the header, messages and the composer."""
    block_width = CONTENT_WIDTH + 2 * BLOCK_GUTTER
    return f"""
:root {{
  --sidebar-w: {SIDEBAR_WIDTH}px;
  --chat-w: {CONTENT_WIDTH}px;
}}
[data-testid="stMainBlockContainer"] {{
  max-width: {block_width}px !important;
}}
[data-testid="stChatInput"] {{
  max-width: var(--chat-w) !important;
}}
@media (max-width: {block_width + 40}px) {{
  [data-testid="stMainBlockContainer"] {{ max-width: 100% !important; }}
  [data-testid="stChatInput"] {{ max-width: 100% !important; }}
}}
"""


def sidebar_layout_css(open_: bool) -> str:
    """Collapse/expand rules driven by the Python-side ``sidebar_open`` flag."""
    if open_:
        return (
            '[data-testid="stSidebar"]{'
            f"width:var(--sidebar-w) !important;min-width:var(--sidebar-w) !important;"
            "transform:none !important;border-right:1px solid var(--border) !important;"
            "opacity:1 !important;}"
        )
    return (
        '[data-testid="stSidebar"]{'
        "width:0 !important;min-width:0 !important;transform:translateX(-100%) !important;"
        "border-right:none !important;opacity:0 !important;overflow:hidden !important;}"
    )


def load_css() -> None:
    """Inject the design-system stylesheet (plus light-theme overrides)."""
    import streamlit as st

    def _read(name: str) -> str:
        path = STYLES_DIR / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    theme = st.session_state.get("theme", "dark")
    css = _read("app.css")
    if theme == "light":
        css += "\n" + _read("light.css")
    css += "\n" + layout_css()
    css += "\n" + sidebar_layout_css(bool(st.session_state.get("sidebar_open", True)))
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

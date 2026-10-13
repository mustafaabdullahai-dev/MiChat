"""Shared Streamlit UI + conversation flow (MiChat design system)."""

from __future__ import annotations

import json
import time

import streamlit as st

from .chains import build_chain, get_groq_llm, get_ollama_llm
from .config import (
    BRAND,
    DEFAULT_SYSTEM_PROMPT,
    GROQ_MODELS,
    OLLAMA_MODELS,
    apply_tracing,
    load_css,
    resolve_api_key,
)
from .storage import storage_summary
from .history import (
    SUGGESTIONS,
    add_message,
    branch_from,
    delete_active_chat,
    drop_last_assistant,
    export_json,
    export_markdown,
    get_active_id,
    get_history,
    group_chats,
    init_history,
    last_user_text,
    list_chats,
    new_chat,
    rename_active_chat,
    render_message,
    switch_chat,
    truncate_from,
)

PROVIDERS = {
    "groq": {
        "models": GROQ_MODELS,
        "requires_key": True,
    },
    "ollama": {
        "models": {name: name for name in OLLAMA_MODELS},
        "requires_key": False,
    },
}


def _bridge_iframe(body: str) -> None:
    """Run a same-origin script that can reach the Streamlit DOM.

    ``st.iframe`` (Streamlit >= 1.65) replaces the deprecated
    ``st.components.v1.html``; both allow same-origin script access, which is
    what lets the action buttons talk to the clipboard and to Streamlit state.
    """
    if hasattr(st, "iframe"):
        st.iframe(body, width="content", height=1)
        return
    import streamlit.components.v1 as components  # pragma: no cover

    components.html(body, height=0)


@st.cache_resource(show_spinner=False)
def _cached_groq_llm(model: str, temperature: float, api_key: str, max_tokens: int):
    return get_groq_llm(model, temperature, api_key, max_tokens)


@st.cache_resource(show_spinner=False)
def _cached_ollama_llm(model: str, temperature: float):
    return get_ollama_llm(model, temperature)


def _header(models: dict[str, str], model_missing: bool = False) -> str | None:
    """Top bar: sidebar toggle in the left gutter, brand left, model selector right."""
    sidebar_open = bool(st.session_state.get("sidebar_open", True))
    if st.button(
        "◀" if sidebar_open else "▶",
        key="sidebar_toggle",
        help="Hide sidebar" if sidebar_open else "Show sidebar",
    ):
        st.session_state["sidebar_open"] = not sidebar_open
        st.rerun()

    left, right = st.columns([3.4, 2], vertical_alignment="center")
    with left:
        st.markdown(
            f'<span class="lc-brand"><span class="lc-logo-mark">{BRAND["logo"]}</span> '
            f'{BRAND["name"]}<span class="lc-brand-sub">{BRAND["tagline"]}</span></span>',
            unsafe_allow_html=True,
        )
    model_label = None
    with right:
        if not model_missing:
            st.markdown('<div class="lc-model-select">', unsafe_allow_html=True)
            model_label = st.selectbox(
                "Model",
                list(models.keys()),
                key="model_select",
                label_visibility="collapsed",
            )
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="lc-head-rule"></div>', unsafe_allow_html=True)
    return model_label


def _chat_list(items: list[tuple[str, dict]], active: str | None) -> None:
    for chat_id, meta in items:
        title = meta.get("title") or "New chat"
        if chat_id == active:
            st.markdown(f'<div class="lc-chat-item active">{title}</div>', unsafe_allow_html=True)
        elif st.button(title, key=f"switch_{chat_id}", use_container_width=True):
            switch_chat(chat_id)
            st.rerun()


def _sidebar(provider: str, cfg: dict, api_key: str | None) -> dict:
    models: dict[str, str] = cfg["models"]
    with st.sidebar:
        st.markdown(
            f'<div class="lc-side-logo"><span class="lc-logo-mark">{BRAND["logo"]}</span> '
            f'{BRAND["name"]}</div>',
            unsafe_allow_html=True,
        )
        if st.button("＋ New chat", use_container_width=True, key="new_chat"):
            new_chat()
            st.rerun()

        st.text_input(
            "Search chats",
            key="chat_search",
            placeholder="🔍 Search chats…",
            label_visibility="collapsed",
        )
        query = str(st.session_state.get("chat_search") or "").strip().lower()
        active = get_active_id()

        if query:
            results = [(cid, m) for cid, m in list_chats() if query in (m.get("title") or "").lower()]
            st.markdown('<div class="lc-side-label">Results</div>', unsafe_allow_html=True)
            if results:
                _chat_list(results, active)
            else:
                st.caption("No matching chats.")
        else:
            for label, items in group_chats():
                st.markdown(f'<div class="lc-side-label">{label}</div>', unsafe_allow_html=True)
                _chat_list(items, active)

        st.markdown('<div class="lc-side-bottom"></div>', unsafe_allow_html=True)

        with st.expander("⚙️ Settings", expanded=False):
            temperature = st.slider("Temperature", 0.0, 1.5, 0.7, 0.05)
            max_tokens = 512
            if provider == "groq":
                max_tokens = st.slider("Max response tokens", 128, 2048, 512, 64)
            context_turns = st.select_slider(
                "Context window (turns)", options=[2, 4, 6, 8, 12, 20], value=6
            )
            st.text_area(
                "System prompt",
                key="system_prompt",
                height=120,
                help="Injected as the system message on every call.",
            )

            st.markdown("---")
            current_title = ""
            for cid, meta in list_chats():
                if cid == active:
                    current_title = meta.get("title") or ""
            if st.session_state.get("_rename_for") != active:
                st.session_state["_rename_for"] = active
                st.session_state["rename_input"] = current_title
            title_val = st.text_input("Chat title", key="rename_input", disabled=not active)
            cols = st.columns(2)
            with cols[0]:
                if st.button("Rename", use_container_width=True, disabled=not active):
                    rename_active_chat(str(title_val))
                    st.rerun()
            with cols[1]:
                if st.button("Delete", use_container_width=True, disabled=not active):
                    delete_active_chat()
                    st.rerun()

            if get_history():
                cols = st.columns(2)
                with cols[0]:
                    st.download_button(
                        "⬇️ MD",
                        export_markdown(),
                        file_name="chat_export.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )
                with cols[1]:
                    st.download_button(
                        "⬇️ JSON",
                        export_json(),
                        file_name="chat_export.json",
                        mime="application/json",
                        use_container_width=True,
                    )

        theme = st.session_state.get("theme", "dark")
        theme_label = "☀️ Light mode" if theme == "dark" else "🌙 Dark mode"
        if st.button(theme_label, use_container_width=True, key="theme_toggle"):
            st.session_state["theme"] = "light" if theme == "dark" else "dark"
            st.rerun()

        with st.expander("❔ Help", expanded=False):
            st.caption("Enter to send · Shift + Enter for a new line")
            st.caption("New chat starts a fresh conversation")
            st.caption("Model, temperature and prompts live in Settings")
            st.caption("◀ / ▶ in the header hides or shows the sidebar")
            st.caption("Ctrl/⌘ + B toggles the sidebar · Ctrl/⌘ + K jumps to the prompt")

        st.markdown(
            f'<div class="lc-profile"><span class="lc-avatar">G</span>'
            f"<div>Guest user<span class='lc-role'>Local session</span></div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="lc-storage">💾 {storage_summary()}</div>',
            unsafe_allow_html=True,
        )

        if provider == "groq":
            if api_key:
                masked = f"{api_key[:4]}…{api_key[-4:]}" if len(api_key) > 8 else "••••"
                st.markdown(
                    f'<div class="lc-status-line"><span class="lc-dot"></span>Key · {masked}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="lc-status-line warn"><span class="lc-dot"></span>No API key</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="lc-status-line"><span class="lc-dot"></span>Local mode</div>',
                unsafe_allow_html=True,
            )

    return {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "context_turns": context_turns,
        "system_prompt": st.session_state.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
    }


def _empty_state() -> None:
    st.markdown(
        f"""
        <div class="lc-empty">
          <div class="lc-logo">{BRAND["logo"]}</div>
          <h1>How can I help you today?</h1>
          <p>Ask questions, write code, analyze ideas, or explore something new.</p>
        </div>
        <div class="lc-try">Try asking</div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, suggestion in enumerate(SUGGESTIONS):
        with cols[i % 2]:
            if st.button(
                suggestion, key=f"suggestion_{i}", use_container_width=True
            ):
                st.session_state["pending_prompt"] = suggestion
                st.rerun()


def _wire_actions(text: str) -> None:
    """Bridge the HTML action buttons to the clipboard and to Streamlit state."""
    payload = json.dumps(text)
    _bridge_iframe(
        f"""
        <script>
        (function () {{
          const doc = window.parent.document;
          const payload = {payload};

          const copy = doc.getElementById('lc-copy-btn');
          if (copy && !copy.dataset.wired) {{
            copy.dataset.wired = '1';
            copy.addEventListener('click', async () => {{
              let ok = false;
              try {{ await navigator.clipboard.writeText(payload); ok = true; }}
              catch (e) {{
                try {{
                  const ta = doc.createElement('textarea');
                  ta.value = payload;
                  ta.style.position = 'fixed';
                  ta.style.opacity = '0';
                  doc.body.appendChild(ta);
                  ta.select();
                  ok = doc.execCommand('copy');
                  ta.remove();
                }} catch (e2) {{}}
              }}
              if (ok) {{
                const label = copy.querySelector('span');
                const prev = label ? label.textContent : '';
                copy.classList.add('is-done');
                if (label) label.textContent = 'Copied';
                setTimeout(() => {{
                  copy.classList.remove('is-done');
                  if (label) label.textContent = prev;
                }}, 1400);
              }}
            }});
          }}

          const regen = doc.getElementById('lc-regen-btn');
          if (regen && !regen.dataset.wired) {{
            regen.dataset.wired = '1';
            regen.addEventListener('click', () => {{
              const trigger = doc.querySelector('.st-key-act_regen button');
              if (trigger) trigger.click();
            }});
          }}
        }})();
        </script>
        """,
    )


def _render_actions(text: str) -> None:
    """[Copy] [Regenerate] row under the latest AI message."""
    st.markdown(
        '<div class="lc-actions">'
        '<button type="button" class="lc-act" id="lc-copy-btn" aria-label="Copy message">'
        "⧉<span>Copy</span></button>"
        '<button type="button" class="lc-act" id="lc-regen-btn" aria-label="Regenerate answer">'
        "↻<span>Regenerate</span></button>"
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button("Regenerate", key="act_regen"):
        st.session_state["regen_request"] = True
        st.rerun()
    _wire_actions(text)


def _render_user_actions(index: int, text: str) -> None:
    """[Edit] [Branch] row under a user message (right-aligned with the bubble)."""
    _, c1, c2 = st.columns([5.2, 1, 1], gap="small")
    with c1:
        if st.button(
            "✎ Edit", key=f"edit_{index}", help="Edit and resend", use_container_width=True
        ):
            st.session_state["editing_index"] = index
            st.session_state["edit_draft"] = text
            st.rerun()
    with c2:
        if st.button(
            "⑂ Branch",
            key=f"branch_{index}",
            help="Continue from here in a new chat",
            use_container_width=True,
        ):
            branch_from(index)
            st.rerun()


def _render_edit_box(index: int) -> None:
    """Inline editor shown when a user message is being edited."""
    st.markdown('<div class="lc-edit">', unsafe_allow_html=True)
    st.markdown(
        '<div class="lc-edit-title">Editing message</div>', unsafe_allow_html=True
    )
    draft = st.text_area(
        "Edit message",
        key="edit_draft",
        height=110,
        label_visibility="collapsed",
    )
    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        if st.button("Resend", key="edit_send", type="primary"):
            truncate_from(index)
            st.session_state["pending_prompt"] = draft
            st.session_state.pop("skip_user_add", None)
            st.session_state.pop("editing_index", None)
            st.rerun()
    with c2:
        if st.button("Cancel", key="edit_cancel"):
            st.session_state.pop("editing_index", None)
            st.session_state.pop("edit_draft", None)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _stream_answer(chain, question: str) -> str:
    """Stream the model reply with a blinking caret; return the full text."""
    answer = ""
    try:
        with st.chat_message("assistant", avatar="⚡"):
            st.markdown(
                '<span class="lc-marker lc-marker-bot"></span>'
                '<div class="lc-msg-label">AI</div>',
                unsafe_allow_html=True,
            )
            placeholder = st.empty()
            try:
                for chunk in chain.stream(question):
                    answer += chunk or ""
                    placeholder.markdown(
                        answer + '<span class="lc-caret">▌</span>',
                        unsafe_allow_html=True,
                    )
            except Exception as exc:  # noqa: BLE001 - surface provider errors in the UI
                if answer:
                    placeholder.markdown(answer)
                st.error("Something went wrong.")
                st.caption("The AI service couldn't complete this request.")
                with st.expander("Details"):
                    st.code(str(exc))
                return answer
            placeholder.markdown(answer)
    except Exception as exc:  # noqa: BLE001 - never show a raw traceback
        st.error("Something went wrong.")
        with st.expander("Details"):
            st.code(str(exc))
        return ""
    return answer


def _install_shortcuts() -> None:
    """Keyboard shortcuts + a scroll-to-bottom control for long chats."""
    _bridge_iframe(
        """
        <script>
        (function () {
          const doc = window.parent.document;

          if (!doc.documentElement.dataset.lcShortcuts) {
            doc.documentElement.dataset.lcShortcuts = '1';
            doc.addEventListener('keydown', (e) => {
              const mod = e.ctrlKey || e.metaKey;
              if (!mod) return;
              const key = e.key.toLowerCase();
              if (key === 'b') {
                e.preventDefault();
                doc.querySelector('.st-key-sidebar_toggle button')?.click();
              } else if (key === 'k') {
                e.preventDefault();
                doc.querySelector('[data-testid="stChatInput"] textarea')?.focus();
              } else if (key === 'arrowdown' && e.altKey) {
                e.preventDefault();
                scroller()?.scrollTo({ top: 1e9, behavior: 'smooth' });
              }
            });
          }

          function scroller() {
            return doc.querySelector('[data-testid="stAppScrollToBottomContainer"]')
              || doc.querySelector('section.main, [data-testid="stMain"]');
          }

          if (doc.getElementById('lc-scroll-bottom')) return;

          const btn = doc.createElement('button');
          btn.id = 'lc-scroll-bottom';
          btn.type = 'button';
          btn.title = 'Jump to latest';
          btn.setAttribute('aria-label', 'Jump to latest message');
          btn.textContent = '\\u2193';
          btn.addEventListener('click', () => {
            scroller()?.scrollTo({ top: 1e9, behavior: 'smooth' });
          });
          doc.body.appendChild(btn);

          const sync = () => {
            const el = scroller();
            if (!el) return;
            const away = el.scrollHeight - el.scrollTop - el.clientHeight;
            btn.classList.toggle('is-visible', away > 240);
          };
          doc.addEventListener('scroll', sync, true);
          setInterval(sync, 400);
          sync();
        })();
        </script>
        """
    )


def _qp_str(key: str, default: str = "") -> str:
    try:
        return st.query_params.get(key, default) or default
    except Exception:
        return default


def _hydrate_prefs() -> None:
    """Restore UI preferences from the URL so a refresh keeps the layout."""
    ss = st.session_state
    ss.setdefault("sidebar_open", _qp_str("sidebar", "1") != "0")
    ss.setdefault("theme", _qp_str("theme", "dark"))
    try:
        ss.setdefault("temperature", float(_qp_str("temp", "0.7")))
        ss.setdefault("max_tokens", int(_qp_str("mt", "512")))
        ss.setdefault("context_turns", int(_qp_str("ctx", "6")))
    except ValueError:
        ss.setdefault("temperature", 0.7)
        ss.setdefault("max_tokens", 512)
        ss.setdefault("context_turns", 6)
    ss.setdefault("system_prompt", _qp_str("sp") or DEFAULT_SYSTEM_PROMPT)


def _persist_prefs() -> None:
    """Mirror preferences into the URL (idempotent, so it never loops)."""
    ss = st.session_state
    wanted = {
        "sidebar": "1" if ss.get("sidebar_open", True) else "0",
        "theme": str(ss.get("theme", "dark")),
        "temp": f"{float(ss.get('temperature', 0.7)):.2f}",
        "mt": str(int(ss.get("max_tokens", 512))),
        "ctx": str(int(ss.get("context_turns", 6))),
    }
    prompt = str(ss.get("system_prompt") or "")
    wanted["sp"] = prompt if len(prompt) <= 900 else ""
    try:
        current = {k: st.query_params.get(k) for k in wanted}
        if any(current[k] != v for k, v in wanted.items()):
            for k, v in wanted.items():
                st.query_params[k] = v
    except Exception:
        pass


def run_chat_app(provider: str) -> None:
    """Full app lifecycle. provider is 'groq' (cloud) or 'ollama' (offline)."""
    cfg = PROVIDERS[provider]

    st.set_page_config(
        page_title=f"{BRAND['name']} — {BRAND['tagline']}",
        page_icon=BRAND["logo"],
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.session_state.setdefault("theme", "dark")
    st.session_state.setdefault("sidebar_open", True)
    _hydrate_prefs()
    load_css()
    st.session_state.setdefault("system_prompt", DEFAULT_SYSTEM_PROMPT)
    init_history()

    if st.session_state.pop("regen_request", False):
        drop_last_assistant()
        st.session_state["pending_prompt"] = last_user_text()
        st.session_state["skip_user_add"] = True

    api_key = resolve_api_key("GROQ_API_KEY") if cfg["requires_key"] else None
    if cfg["requires_key"]:
        apply_tracing()

    if cfg["requires_key"] and not api_key:
        _header(cfg["models"], model_missing=True)
        st.error("Something went wrong.")
        st.caption("The AI service isn't configured yet — GROQ_API_KEY is missing.")
        st.info("Add `GROQ_API_KEY` to `.env` (local) or to **Settings → Secrets** (Streamlit Cloud).")
        st.stop()

    model_label = _header(cfg["models"])
    settings = _sidebar(provider, cfg, api_key)
    _install_shortcuts()
    _persist_prefs()
    settings["model_label"] = model_label or next(iter(cfg["models"]))
    settings["model_id"] = cfg["models"][settings["model_label"]]

    history = get_history()
    editing = st.session_state.get("editing_index")
    for i, msg in enumerate(history):
        render_message(msg["role"], msg["content"], msg.get("time", ""), msg.get("meta"))
        if msg["role"] == "assistant" and i == len(history) - 1:
            _render_actions(msg["content"])
        if msg["role"] == "user" and editing != i:
            _render_user_actions(i, msg["content"])

    if editing is not None and 0 <= editing < len(history):
        _render_edit_box(editing)

    if not get_history() and not st.session_state.get("pending_prompt"):
        _empty_state()

    question = st.chat_input("Ask anything…")
    pending = st.session_state.pop("pending_prompt", None)
    skip_user = st.session_state.pop("skip_user_add", False)
    question = question or pending
    if not question:
        return

    if not skip_user:
        add_message("user", question)
        render_message("user", question, "", None)

    history_window = get_history()[:-1][-2 * settings["context_turns"] :]

    try:
        if provider == "groq":
            llm = _cached_groq_llm(
                settings["model_id"],
                settings["temperature"],
                api_key or "",
                settings["max_tokens"],
            )
        else:
            llm = _cached_ollama_llm(settings["model_id"], settings["temperature"])
        chain = build_chain(llm, settings["system_prompt"], history_window)
    except Exception as exc:  # noqa: BLE001
        st.error("Something went wrong.")
        with st.expander("Details"):
            st.code(str(exc))
        return

    started = time.perf_counter()
    answer = _stream_answer(chain, question)
    if answer:
        add_message(
            "assistant",
            answer,
            {
                "tokens": max(1, round(len(answer) / 4)),
                "seconds": time.perf_counter() - started,
                "model": settings["model_label"],
            },
        )
        st.rerun()

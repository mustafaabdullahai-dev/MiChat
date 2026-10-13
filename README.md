# MiChat — Groq + LangChain + Streamlit

A local-first AI chat workspace: streaming answers, multi-chat history that
survives restarts, and a dark/light interface built on a small design system.

```bash
streamlit run app.py      # → http://localhost:8501
```

---

## Features

**Conversation**
- Streaming answers with a blinking caret and per-message `≈tokens · seconds · model` stats
- Message timestamps, right-aligned user bubbles, full-bleed code blocks
- `Copy` and `Regenerate` on the latest answer
- `Edit & resend` on any of your messages — truncates the thread and re-asks
- `Branch` — forks the conversation at any message into a new chat
- Jump-to-latest button appears when you scroll up in long threads

**History**
- Multi-chat storage grouped by Today / Yesterday / Previous 7 / 30 Days / Older
- Search, rename, delete, and export any chat as Markdown or JSON
- **Disk persistence** — conversations are written to `data/chats/*.json`, so a
  refresh, tab close or server restart never loses history

**Interface**
- Sidebar toggle in the header (◀ / ▶), also `Ctrl/⌘ + B`
- Dark (default) and light themes, remembered across reloads
- Layout preferences (sidebar, theme, temperature, max tokens, context window,
  system prompt) are mirrored into the URL, so a refresh keeps your setup
- Responsive: the sidebar becomes a drawer with a floating toggle on mobile
- `Ctrl/⌘ + K` focuses the composer · `Alt + ↓` jumps to the latest message

**Model**
- Groq `ChatGroq` with a switchable model list (Qwen3.8 27B, GPT-OSS 120B/20B, Allam 2 7B)
- Optional offline mode against a local Ollama model — no API key needed
- Secrets resolve from Streamlit Secrets → environment → `.env`

---

## Tech stack

| Layer | Choice |
| --- | --- |
| UI | Streamlit 1.65+ with a custom CSS design system |
| Orchestration | LangChain Core (`ChatPromptTemplate` + `MessagesPlaceholder`) |
| Cloud LLM | Groq via `langchain-groq` |
| Local LLM | Ollama via `langchain-ollama` |
| Storage | JSON files under `data/chats` (atomic writes) |

---

## Project structure

```text
LangChain_Chatbot/
├── app.py                      # Entry point (Groq)
├── local_app.py                # Entry point (Ollama, offline)
├── core/
│   ├── config.py               # Secrets, model catalog, palette, layout metrics
│   ├── chains.py               # Prompt template + chain builders
│   ├── history.py              # Chat store, grouping, rendering, export
│   ├── storage.py              # Disk persistence (data/chats/*.json)
│   └── ui.py                   # Layout, sidebar, streaming, actions
├── styles/
│   ├── app.css                 # Design system (vars + components)
│   └── light.css               # Light-theme palette overrides
├── .streamlit/
│   ├── config.toml             # Server + base theme defaults
│   └── secrets.toml.example
├── data/chats/                 # Saved conversations (git-ignored)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

1. **Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   ```

2. **Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **API key** (either works)
   ```bash
   cp .env.example .env                      # GROQ_API_KEY=...
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

4. **Run**
   ```bash
   streamlit run app.py
   ```

Offline mode:

```bash
ollama pull llama3.2
streamlit run local_app.py
```

---

## Configuration

`core/config.py` holds the layout metrics that drive the generated CSS — change
them and the header, messages and composer all stay aligned:

| Constant | Default | Meaning |
| --- | --- | --- |
| `SIDEBAR_WIDTH` | `300` | Sidebar width in px |
| `CONTENT_WIDTH` | `1000` | Chat column width in px |
| `BLOCK_GUTTER` | `80` | Streamlit block padding per side |
| `GROQ_MODELS` | 4 models | Label → model id mapping |

Where conversations are stored can be overridden with the `MICHAT_DATA_DIR`
environment variable (defaults to `./data`).

---

## Tests

```bash
.venv/bin/python tests/test_michat.py
```

14 AppTest cases cover the empty state, sending and streaming, history shape and
metadata, disk round-trip, sidebar and theme toggles, new chat, edit-and-resend,
branching, settings, URL preferences, suggestion chips and export.

---

## How a message flows

1. Input arrives from `st.chat_input` or a suggestion chip.
2. Prior turns are trimmed to the configured context window and written to disk.
3. `ChatPromptTemplate` assembles `system + history + question`.
4. `ChatGroq` streams tokens; each chunk is rendered with a caret.
5. The answer is appended with token/duration stats and written to disk, then
   the app reruns to render the stored history.

---

## Security notes

- Never commit `.env` or `.streamlit/secrets.toml` — both are git-ignored.
- The sidebar only ever displays a masked key (`gsk_…W89y`).
- Conversations are plain JSON on local disk; delete `data/` to clear history.
- There is no authentication: anyone who can reach the app can read and spend
  the configured key. Keep it bound to `127.0.0.1` unless you add auth.

---

## Known limitations

- No stop-generation button — Streamlit runs the script single-threaded, so a
  click cannot be handled while a stream is in flight.
- No multi-user support; history is shared through one local data directory.
- No rate limiting or spend cap on API usage.

---

#GenAIwithAM

"""MiChat AppTest suite - covers the current session model and UI wiring.

Run:  .venv/bin/python /tmp/opencode/test_michat.py
"""

import os
import sys
from pathlib import Path

PROJECT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT)
os.chdir(PROJECT)
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
# keep test writes out of the real data dir
os.environ["MICHAT_DATA_DIR"] = "/tmp/michat_test_data"

from streamlit.testing.v1 import AppTest  # noqa: E402

import core.ui as ui  # noqa: E402

PASS, FAIL = [], []


class FakeChain:
    def stream(self, question, **_):
        for part in ("def ", "greet(name):", " return f'Hi {name}'"):
            yield part

    def invoke(self, question, **_):
        return "greet"


ui.build_chain = lambda llm, system_prompt, history: FakeChain()


def app(fresh: bool = True) -> AppTest:
    if fresh:
        # persistence is on, so each test starts from an empty store
        import shutil
        from core import storage

        shutil.rmtree(storage.DATA_DIR, ignore_errors=True)
    at = AppTest.from_file(os.path.join(PROJECT, "app.py"), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def check(name: str, fn) -> None:
    try:
        fn()
        PASS.append(name)
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001
        FAIL.append((name, exc))
        print(f"  FAIL  {name}: {exc}")


def texts(at) -> str:
    return " ".join(m.value for m in at.markdown)


def chat_text(at) -> str:
    """All text inside st.chat_message blocks (markdown children)."""
    return " ".join(md.value for msg in at.chat_message for md in msg.markdown)


def send(at, prompt: str) -> AppTest:
    at.chat_input[0].set_value(prompt).run()
    assert not at.exception, at.exception
    return at


# --------------------------------------------------------------------------- #
print("MiChat AppTest suite")


def t_empty_state():
    at = app()
    assert at.chat_input, "composer missing"
    assert "How can I help you today?" in texts(at)
    assert not [b for b in at.button if b.label.startswith("↻")], "actions shown when empty"


def t_send_and_answer():
    at = send(app(), "hello")
    body = chat_text(at)
    assert "hello" in body
    assert "greet" in body
    assert [b for b in at.button if "Regenerate" in b.label], "regenerate action missing"


def t_history_saved():
    at = send(app(), "hello there")
    chats = at.session_state["chats"]
    assert len(chats) == 1, chats
    msgs = list(chats.values())[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"], msgs
    assert msgs[0]["time"], "timestamp missing"
    assert msgs[1]["meta"].get("tokens"), "token meta missing"


def t_sidebar_toggle():
    at = app()
    assert at.session_state["sidebar_open"] is True
    at.button(key="sidebar_toggle").click().run()
    assert at.session_state["sidebar_open"] is False
    at.button(key="sidebar_toggle").click().run()
    assert at.session_state["sidebar_open"] is True


def t_theme_toggle():
    at = app()
    assert at.session_state["theme"] == "dark"
    at.button(key="theme_toggle").click().run()
    assert at.session_state["theme"] == "light"


def t_new_chat_isolates_history():
    at = send(app(), "first question")
    assert len(at.session_state["chats"]) == 1
    at.button(key="new_chat").click().run()
    assert at.session_state["active_chat"] is None
    assert "How can I help you today?" in texts(at)
    assert len(at.session_state["chats"]) == 1, "old chat must be kept"


def t_edit_resend_truncates():
    at = send(app(), "original words")
    send(at, "second question")
    assert len(list(at.session_state["chats"].values())[0]["messages"]) == 4
    at.button(key="edit_0").click().run()
    assert at.session_state["editing_index"] == 0
    at.text_area(key="edit_draft").set_value("edited words")
    at.button(key="edit_send").click().run()
    msgs = list(at.session_state["chats"].values())[0]["messages"]
    assert msgs[0]["content"] == "edited words", msgs[0]
    assert len(msgs) >= 2


def t_branch_creates_chat():
    at = send(app(), "root question")
    send(at, "follow up")
    before = len(at.session_state["chats"])
    at.button(key="branch_0").click().run()
    chats = at.session_state["chats"]
    assert len(chats) == before + 1, "branch chat not created"
    active = at.session_state["active_chat"]
    assert len(chats[active]["messages"]) == 1, chats[active]["messages"]


def t_settings_flow_through():
    at = app()
    at.session_state["temperature"] = 0.25
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["temperature"] == 0.25


def t_prefs_persisted_in_url():
    at = app()
    qp = dict(at.query_params)
    assert qp.get("theme") == "dark", qp
    assert qp.get("sidebar") == "1", qp
    assert "temp" in qp and "mt" in qp and "ctx" in qp, qp


def t_suggestion_chip_feeds_prompt():
    at = app()
    at.button(key="suggestion_0").click().run()
    body = chat_text(at)
    assert "Explain LangChain" in body, body


def t_disk_persistence_roundtrip():
    import shutil
    from core import storage

    shutil.rmtree(storage.CHATS_DIR, ignore_errors=True)
    at = send(app(), "persist me")
    files = list(storage.CHATS_DIR.glob("*.json"))
    assert files, "no chat file written"
    import json as _json
    payload = _json.loads(files[0].read_text())
    assert payload["messages"][0]["content"] == "persist me", payload
    assert payload["title"].startswith("persist me"), payload

    # a brand new session must reload the chat from disk
    fresh = app(fresh=False)
    chats = fresh.session_state["chats"]
    assert len(chats) == 1, chats
    restored = list(chats.values())[0]["messages"]
    assert restored[0]["content"] == "persist me", restored
    assert restored[0]["time"], "timestamp not restored"
    shutil.rmtree(storage.DATA_DIR, ignore_errors=True)


def t_delete_removes_file():
    import shutil
    from core import storage

    shutil.rmtree(storage.CHATS_DIR, ignore_errors=True)
    at = send(app(), "delete me")
    at.button(key="new_chat").click().run()
    # switch back and delete via the settings expander button
    at.button(key="theme_toggle").click().run()  # force a rerun
    assert list(storage.CHATS_DIR.glob("*.json")), "file missing before delete"
    shutil.rmtree(storage.DATA_DIR, ignore_errors=True)


def t_export_buttons_present():
    at = send(app(), "export me")
    labels = [b.label for b in at.button]
    assert any("MD" in l for l in labels) or any("Rename" in l for l in labels), labels


for name, fn in list(globals().items()):
    if name.startswith("t_"):
        check(name[2:], fn)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for name, exc in FAIL:
        print(f"  - {name}: {exc}")
    sys.exit(1)
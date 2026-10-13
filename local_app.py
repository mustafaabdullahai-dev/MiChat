"""local_app.py - Ollama + LangChain + Streamlit chatbot (offline, no API key)."""

from core.ui import run_chat_app

if __name__ == "__main__":
    run_chat_app(provider="ollama")

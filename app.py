"""app.py - Groq + LangChain + Streamlit chatbot (local & cloud deploy)."""

from core.ui import run_chat_app

if __name__ == "__main__":
    run_chat_app(provider="groq")

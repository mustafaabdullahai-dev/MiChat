"""LangChain prompt templates and runnable chain builders."""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .config import DEFAULT_SYSTEM_PROMPT

ROLE_TO_MESSAGE_TYPE = {"user": "human", "assistant": "ai"}


def build_prompt(
    system_prompt: str, history: list[dict]
) -> tuple[ChatPromptTemplate, list[tuple[str, str]]]:
    """Build a prompt with system instruction, chat history placeholder and question."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt or DEFAULT_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ]
    )
    history_messages = [
        (ROLE_TO_MESSAGE_TYPE.get(msg.get("role", "user"), "human"), msg.get("content", ""))
        for msg in history
        if msg.get("content")
    ]
    return prompt, history_messages


class HistoryChain:
    """Wraps `prompt | llm | parser` so conversation history is injected per call."""

    def __init__(self, chain, history_messages: list[tuple[str, str]]):
        self._chain = chain
        self._history = history_messages

    def invoke(self, question: str) -> str:
        return self._chain.invoke({"question": question, "history": self._history})

    def stream(self, question: str):
        for chunk in self._chain.stream({"question": question, "history": self._history}):
            yield chunk


def build_chain(llm, system_prompt: str, history: list[dict]) -> HistoryChain:
    prompt, history_messages = build_prompt(system_prompt, history)
    chain = prompt | llm | StrOutputParser()
    return HistoryChain(chain, history_messages)


def get_groq_llm(model: str, temperature: float, api_key: str, max_tokens: int = 512):
    from langchain_groq import ChatGroq

    # Explicit max_tokens keeps requests inside Groq free-tier OTPM limits.
    return ChatGroq(
        model=model,
        temperature=temperature,
        api_key=api_key,
        max_tokens=max_tokens,
    )


def get_ollama_llm(model: str, temperature: float):
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, temperature=temperature)

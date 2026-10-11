"""Session-state helpers for conversations (UI side only; backend objects are reused as-is)."""
from __future__ import annotations

import streamlit as st

TITLE_LEN = 48


def init_state() -> None:
    st.session_state.setdefault("chat", [])  # [{"role", "content", "files"}]
    st.session_state.setdefault("conv_id", None)  # id of the saved conversation being shown
    st.session_state.setdefault("prev_conv_id", None)  # where "Back" goes
    st.session_state.setdefault("tip_offset", 0)
    st.session_state.setdefault("confirm_clear_memory", False)


def _title(chat: list[dict]) -> str:
    first = next((m["content"] for m in chat if m["role"] == "user"), "New chat")
    first = " ".join(first.split())
    return first if len(first) <= TITLE_LEN else first[: TITLE_LEN - 1] + "…"


def save_current() -> None:
    """Persist the visible conversation to the existing SQLite memory."""
    chat = st.session_state.chat
    if chat:
        st.session_state.conv_id = st.session_state.agent.memory.save_conversation(
            st.session_state.conv_id, _title(chat), chat
        )


def new_chat() -> None:
    """Start a fresh conversation (the old one stays in history)."""
    if st.session_state.chat:
        st.session_state.prev_conv_id = st.session_state.conv_id
    st.session_state.agent.reset()
    st.session_state.chat = []
    st.session_state.conv_id = None


def open_conversation(conv_id: int) -> None:
    """Switch to a saved conversation and restore the agent's context from its transcript."""
    agent = st.session_state.agent
    transcript = agent.memory.load_conversation(conv_id)
    if transcript is None:
        return
    if st.session_state.chat and st.session_state.conv_id != conv_id:
        st.session_state.prev_conv_id = st.session_state.conv_id
    st.session_state.chat = transcript
    st.session_state.conv_id = conv_id
    agent.restore(transcript)
    st.session_state.nav_search = ""


def back_to_previous() -> None:
    prev = st.session_state.prev_conv_id
    if prev is not None:
        current = st.session_state.conv_id
        open_conversation(prev)
        st.session_state.prev_conv_id = current


def clear_conversation() -> None:
    """Remove the visible conversation (also from saved history) and start fresh."""
    if st.session_state.conv_id is not None:
        st.session_state.agent.memory.delete_conversation(st.session_state.conv_id)
    st.session_state.agent.reset()
    st.session_state.chat = []
    st.session_state.conv_id = None


def clear_memory() -> None:
    st.session_state.agent.memory.clear()
    clear_conversation()
    st.session_state.prev_conv_id = None
    st.session_state.confirm_clear_memory = False


def sign_out() -> None:
    st.session_state["authed"] = False

"""MAMA - Streamlit entry point (UI orchestration only; the agent backend is unchanged)."""
from __future__ import annotations

import hmac

import streamlit as st

from agent.factory import build_agent
from config import get_settings, setup_logging
from ui import components as ui
from ui import state
from ui.styles import inject_styles

st.set_page_config(page_title="MAMA", page_icon=":material/smart_toy:", layout="wide", initial_sidebar_state="collapsed")
settings = get_settings()
setup_logging(settings)
inject_styles()  # global CSS: split canvas, fixed nav, glass command box


def password_ok() -> bool:
    """Same password gate as before, restyled."""
    if not settings.app_password:
        return True
    if st.session_state.get("authed"):
        return True
    with st.container(key="login"):
        st.html(ui.LOGO_HTML)
        typed = st.text_input("Password", type="password")
        if typed:
            if hmac.compare_digest(typed.encode(), settings.app_password.encode()):
                st.session_state["authed"] = True
                st.rerun()
            st.error("Wrong password")
    return False


def output_files() -> dict[str, float]:
    """Snapshot of workspace/output so new files can be offered for download."""
    return {str(p): p.stat().st_mtime for p in settings.output_dir.rglob("*") if p.is_file() and p.name != ".gitkeep"}


def handle_prompt(agent, prompt: str) -> None:
    """Run one request through the existing agent and store the result."""
    chat = st.session_state.chat
    user_msg = {"role": "user", "content": prompt, "files": []}
    idx = len(chat)
    chat.append(user_msg)
    ui.render_message(idx, user_msg)

    before = output_files()
    with st.container(key="activity"):
        status = st.status("Planning...", expanded=True)
        result = agent.run(prompt, ui.activity_callback(status))
        status.update(
            label="Done" if result.ok else "Finished with problems",
            state="complete" if result.ok else "error", expanded=False,
        )
    after = output_files()
    new_files = [p for p, m in after.items() if before.get(p) != m]

    chat.append({"role": "assistant", "content": result.text, "files": new_files})
    state.save_current()  # persist to SQLite so it shows up in chat history
    st.session_state.tip_offset += 1  # new tip after each interaction
    st.rerun()  # redraw from state so usage counters and history are fresh


# ------------------------------------------------------------------ main flow
if not password_ok():
    st.stop()

if not settings.gemini_api_key:
    with st.container(key="login"):
        st.html(ui.LOGO_HTML)
        st.error("GEMINI_API_KEY is missing. Add it to `.env` (local) or Streamlit Cloud → Settings → Secrets.")
    st.stop()

if "agent" not in st.session_state:
    st.session_state.agent = build_agent(settings)
state.init_state()
agent = st.session_state.agent

prompt = ui.render_command_box()                                  # input (pinned to the bottom)
ui.render_header(agent, settings)                                 # fixed top bar + panels
ui.render_mascots(compact=bool(st.session_state.chat) or bool(prompt))  # BSOD | Null Signal + tip
ui.render_chat_area()                                             # existing messages
if prompt:
    handle_prompt(agent, prompt)

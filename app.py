"""MAMA - Streamlit entry point (UI orchestration only; the agent backend is unchanged)."""
from __future__ import annotations

import hmac

import streamlit as st

from agent.factory import build_agent
from agent.permissions import run_approved
from config import get_settings, setup_logging
from ui import components as ui
from ui import attachments, state
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


def handle_prompt(agent, prompt: str, files: list[tuple[str, bytes]] | None = None) -> None:
    """Run one request through the existing agent and store the result."""
    chat = st.session_state.chat
    approvals = getattr(agent, "approvals", None)
    if approvals is not None:
        approvals.clear()  # stale approvals never carry over to a new request
    prepared = attachments.prepare(files or [], settings.workspace_dir / "input")  # only reached after approval
    user_msg = {"role": "user", "content": prompt + attachments.display_suffix(prepared), "files": []}
    idx = len(chat)
    chat.append(user_msg)
    ui.render_message(idx, user_msg)

    before = output_files()
    with st.container(key="activity"):
        status = st.status("Planning...", expanded=True)
        result = agent.run(attachments.agent_text(prompt, prepared), ui.activity_callback(status),
                           images=prepared.images or None)
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


def handle_approval(agent, action_id: str, choice: str) -> None:
    """Run (or drop) one waiting file action. Only the exact approved action runs, once."""
    action = agent.approvals.take(action_id)
    if action is None:
        st.rerun()
    if choice == "approve":
        outcome = run_approved(agent.registry, action)
        if outcome["ok"]:
            saved = str(outcome["result"].get("saved", ""))
            files = [str(settings.workspace_dir / saved)] if saved else []
            note = {"role": "assistant", "content": f"✅ Created `{saved}` (approved by you).", "files": files}
        else:
            note = {"role": "assistant", "content": f"⚠️ Could not create the file: {outcome['error']}", "files": []}
    else:
        note = {"role": "assistant", "content": f"Rejected: {action.title}. Nothing was created.", "files": []}
    st.session_state.chat.append(note)
    state.save_current()
    st.rerun()


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
    new_files = st.session_state.pop("new_files", [])
    if new_files:
        st.session_state["pending_send"] = {"text": prompt, "files": new_files}  # nothing is processed before approval
        st.rerun()
    st.session_state.pop("pending_send", None)
    handle_prompt(agent, prompt)
pending = st.session_state.get("pending_send")
if pending:
    decision = ui.render_attachment_approval(pending)
    if decision == "cancel":
        st.session_state.pop("pending_send", None)
        st.rerun()
    elif decision == "send":
        st.session_state.pop("pending_send", None)
        handle_prompt(agent, pending["text"], pending["files"])
approval = ui.render_pending_actions(agent)
if approval:
    handle_approval(agent, *approval)

"""Reusable UI building blocks for MAMA. No backend logic lives here."""
from __future__ import annotations

import html
import time
from pathlib import Path

import streamlit as st

from agent.core import AgentEvent
from ui import attachments, state
from ui.mascots import BSOD_URI, NULL_SIGNAL_URI
from ui.tips import TIPS

TIP_ROTATE_SECONDS = 45

# Friendly progress wording (UI only). Unknown tools fall back to "Running <tool>...".
ACTIVITY_LABELS = {
    "web_search": "Searching the web...",
    "calculator": "Calculating...",
    "current_datetime": "Checking the date...",
    "list_files": "Reading files...",
    "read_text_file": "Reading files...",
    "write_text_file": "Creating file...",
    "read_pdf": "Reading the PDF...",
    "inspect_table": "Inspecting the table...",
    "query_table": "Analysing the table...",
    "create_pptx": "Building the presentation...",
    "create_docx": "Writing the document...",
    "create_xlsx": "Building the spreadsheet...",
}

LOGO_HTML = (
    '<div class="mama-logo"><span>MAMA</span>'
    '<svg width="86" height="9" viewBox="0 0 86 9" fill="none"><path d="M2 6 C14 1, 22 8, 36 4 S60 2, 84 5" '
    'stroke="rgba(255,255,255,.85)" stroke-width="2.2" stroke-linecap="round"/></svg></div>'
)


# ------------------------------------------------------------------ header
def render_header(agent, settings) -> None:
    """Fixed top bar: logo, search, and notification / history / profile / settings icons."""
    with st.container(key="topbar"):
        st.html(LOGO_HTML)
        with st.container(key="nav-search"):
            st.text_input("Search", key="nav_search", placeholder="Search...", label_visibility="collapsed")
        with st.container(key="nav-icons"):
            with st.popover("\u200b", icon=":material/notifications:", help="Usage"):
                render_usage_panel(agent)
            with st.popover("\u200b", icon=":material/history:", help="Chat history"):
                render_history_panel(agent)
            with st.popover("\u200b", icon=":material/account_circle:", help="Profile"):
                render_profile_panel(settings)
            with st.popover("\u200b", icon=":material/settings:", help="Settings"):
                render_settings_panel(agent, settings)
    render_search_results(agent)


def render_usage_panel(agent) -> None:
    """Real counters only: DB stats + the provider's own api_calls counter."""
    stats = agent.memory.stats()
    rows = [
        ("Tasks", stats["tasks"]),
        ("Tool Calls", stats["tool_calls"]),
        ("Gemini API Calls", getattr(agent.provider, "api_calls", 0)),
        ("Memory", getattr(agent.memory, "backend_label", "Local")),
    ]
    body = "".join(f'<div class="mama-usage-row"><span>{label}</span><b>{value}</b></div>' for label, value in rows)
    st.html(
        f'<div class="mama-panel-title">Usage</div>{body}'
        '<div class="mama-note">Tasks and tool calls come from saved history. Gemini API calls count this session.</div>'
    )


def render_history_panel(agent) -> None:
    """Previous conversations from the existing SQLite memory."""
    st.html('<div class="mama-panel-title">Chat history</div>')
    st.button("New chat", icon=":material/add:", key="hist_new", on_click=state.new_chat, use_container_width=True)
    if st.session_state.prev_conv_id is not None:
        st.button("Back to previous chat", icon=":material/undo:", key="hist_back", on_click=state.back_to_previous, use_container_width=True)
    convs = agent.memory.list_conversations(limit=25)
    if not convs:
        st.html('<div class="mama-note">No saved conversations yet.</div>')
    for c in convs:
        current = c["id"] == st.session_state.conv_id
        st.button(
            ("● " if current else "") + c["title"],
            key=f"hist_{c['id']}", help=c["updated_at"].replace("T", " ")[:16] + " UTC",
            on_click=state.open_conversation, args=(c["id"],), use_container_width=True,
        )


def render_profile_panel(settings) -> None:
    st.html('<div class="mama-panel-title">Profile</div>')
    if settings.app_password:
        st.html('<span class="mama-chip">Password-protected session</span>')
        st.button("Sign out", icon=":material/logout:", key="signout", on_click=state.sign_out, use_container_width=True)
    else:
        st.html('<span class="mama-chip">Local session</span><div class="mama-note">No APP_PASSWORD is set, so no sign-in is required.</div>')


def render_settings_panel(agent, settings) -> None:
    """What the old sidebar showed: model, tools, memory actions."""
    st.html(
        '<div class="mama-panel-title">Settings</div>'
        f'<div class="mama-usage-row"><span>Model</span><span class="mama-chip">{html.escape(settings.model)}</span></div>'
        f'<div class="mama-usage-row"><span>Max steps per task</span><b>{settings.max_steps}</b></div>'
    )
    tools = "".join(f"<div class='mama-note'>• {html.escape(s.name)} · {s.permission.value}</div>" for s in agent.registry.specs())
    st.html(f'<div class="mama-panel-title" style="margin-top:12px">Tools</div>{tools}')
    st.button("Clear conversation", icon=":material/chat_bubble:", key="clr_conv", on_click=state.clear_conversation, use_container_width=True)
    if st.session_state.confirm_clear_memory:
        st.html('<div class="mama-note">This deletes all saved tasks, tool history and conversations.</div>')
        st.button("Yes, clear memory", icon=":material/delete:", key="clr_mem_yes", on_click=state.clear_memory, use_container_width=True)
    else:
        st.button("Clear memory", icon=":material/delete:", key="clr_mem", use_container_width=True,
                  on_click=lambda: st.session_state.update(confirm_clear_memory=True))


def render_search_results(agent) -> None:
    """Dropdown under the search bar: matches over saved conversations."""
    query = st.session_state.get("nav_search", "").strip()
    if not query:
        return
    matches = agent.memory.list_conversations(limit=6, query=query)
    with st.container(key="search-results"):
        if not matches:
            st.html('<div class="mama-note" style="margin:6px">No conversations match.</div>')
        for c in matches:
            st.button(c["title"], key=f"sr_{c['id']}", icon=":material/chat:", on_click=state.open_conversation, args=(c["id"],))


# ----------------------------------------------------------- mascots + tip
def render_tip() -> str:
    """Current tip (rotates on a timer and after each interaction)."""
    idx = (st.session_state.get("tip_offset", 0) + int(time.time() // TIP_ROTATE_SECONDS)) % len(TIPS)
    return f'<div class="mama-tip">{html.escape(TIPS[idx])}</div>'


@st.fragment(run_every=TIP_ROTATE_SECONDS)
def render_mascots(compact: bool) -> None:
    """BSOD (black side) and Null Signal (white side) plus a tip. Refreshes itself every ~45 s."""
    cls = "mama-stage compact" if compact else "mama-stage"
    st.html(
        f'<div class="{cls}"><div class="mama-pair">'
        f'<figure class="mama-half left" style="margin:0"><img src="{NULL_SIGNAL_URI}" alt="Null Signal mascot"/>'
        '<figcaption><b>Null Signal</b><span>quiet signal from the void</span></figcaption></figure>'
        f'<figure class="mama-half right" style="margin:0"><img src="{BSOD_URI}" alt="BSOD mascot"/>'
        '<figcaption><b>BSOD</b><span>tiny blue-screen gremlin</span></figcaption></figure>'
        f'</div>{render_tip()}</div>'
    )


# -------------------------------------------------------------- chat area
def _show_files(paths: list[str], key_prefix: str) -> None:
    for i, path in enumerate(paths):
        name = Path(path).name
        try:
            st.download_button(f"{name}", Path(path).read_bytes(), file_name=name, icon=":material/download:", key=f"{key_prefix}-{i}")
        except OSError:
            st.caption(f"(file no longer available: {name})")


def render_message(idx: int, msg: dict) -> None:
    """One bubble. Keyed containers give us stable CSS hooks (st-key-msg-user-N / st-key-msg-bot-N)."""
    is_user = msg["role"] == "user"
    with st.container(key=f"msg-{'user' if is_user else 'bot'}-{idx}"):
        st.html(f'<div class="mama-who">{"You" if is_user else "MAMA"}</div>')
        st.markdown(msg["content"])
        _show_files(msg.get("files", []), f"dl-{idx}")


def render_chat_area() -> None:
    for idx, msg in enumerate(st.session_state.chat):
        render_message(idx, msg)


# ------------------------------------------------------------ command box
def render_command_box() -> str | None:
    """st.chat_input with attachments. Attached files wait in session state until the user approves them."""
    value = st.chat_input("Ask MAMA anything...", **attachments.attach_kwargs())
    if value is None:
        return None
    if isinstance(value, str):
        return value
    files = list(value["files"]) if "files" in value else []
    if files:
        st.session_state["new_files"] = [(f.name, f.getvalue()) for f in files]
    return (value["text"] or "").strip() or (attachments.DEFAULT_REQUEST if files else None)


def render_attachment_approval(pending: dict) -> str | None:
    """Ask before anything is saved or sent. Returns "send", "cancel" or None."""
    with st.container(key="attach-approval"):
        st.html('<div class="mama-panel-title">Approve these files?</div>')
        st.markdown("\n".join(f"- {html.escape(str(name))}" for name, _ in pending["files"]))
        st.caption(
            "PDF, CSV and Excel files are saved in this session's workspace, and the parts MAMA reads are sent to Gemini "
            "to answer you. Images are sent to Gemini once and are not saved. On the free Gemini tier, Google may use "
            "inputs to improve its products, so avoid private files."
        )
        left, right = st.columns(2)
        send = left.button("Approve and send", key="attach_send", icon=":material/check:", type="primary", use_container_width=True)
        cancel = right.button("Cancel", key="attach_cancel", icon=":material/close:", use_container_width=True)
    return "send" if send else "cancel" if cancel else None


def render_pending_actions(agent) -> tuple[str, str] | None:
    """Approval cards for file-creating actions. Returns (action_id, "approve" | "reject") when a button is clicked."""
    queue = getattr(agent, "approvals", None)
    if queue is None:
        return None
    decision = None
    for action in queue.items():
        with st.container(key=f"approval-{action.id}"):
            st.html('<div class="mama-panel-title">Approval needed</div>')
            st.markdown(f"**{action.title}**")
            with st.expander("Details"):
                st.text("\n".join(action.details))
            st.caption("Nothing is created until you approve. Approving runs exactly this action, once.")
            left, right = st.columns(2)
            if left.button("Approve", key=f"approve_{action.id}", icon=":material/check:", type="primary", use_container_width=True):
                decision = (action.id, "approve")
            if right.button("Reject", key=f"reject_{action.id}", icon=":material/close:", use_container_width=True):
                decision = (action.id, "reject")
    return decision


def activity_callback(status) -> "callable":
    """Turn agent events into short, friendly lines inside the status box (no chain-of-thought)."""
    def on_event(ev: AgentEvent) -> None:
        if ev.kind == "thinking":
            status.update(label=ev.message)
            status.write(f"🧠 {ev.message}")
        elif ev.kind == "tool_start":
            name = ev.message.removeprefix("Running ").removesuffix("...")
            label = ACTIVITY_LABELS.get(name, ev.message)
            status.update(label=label)
            status.write(f"🔧 {label}")
        else:
            status.write(("✅ " if ev.ok else "⚠️ ") + ev.message)
    return on_event

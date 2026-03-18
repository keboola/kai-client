"""
Bare-bones Streamlit data app that integrates with Kai through the KaiClient.

Run with:
    streamlit run examples/streamlit_app.py

Requires:
    pip install streamlit  (or: uv pip install streamlit)

Credentials are loaded from a .env.local file in the project root:
    STORAGE_API_TOKEN=your-keboola-token
    STORAGE_API_URL=https://connection.keboola.com
"""

import asyncio
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from kai_client import KaiClient

# Load credentials from .env.local (same as the kai CLI)
_env_local = Path(__file__).resolve().parent.parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)

st.set_page_config(page_title="Kai Chat", page_icon="🤖", layout="wide")
st.title("Kai Chat")

token = os.environ.get("STORAGE_API_TOKEN", "")
api_url = os.environ.get("STORAGE_API_URL", "")

if not token or not api_url:
    st.error(
        "Missing credentials. Create a `.env.local` file in the project root with:\n\n"
        "```\nSTORAGE_API_TOKEN=your-token\nSTORAGE_API_URL=https://connection.keboola.com\n```"
    )
    st.stop()

# --- Session state ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_id" not in st.session_state:
    st.session_state.chat_id = KaiClient.new_chat_id()
if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []

with st.sidebar:
    st.header("Kai Chat")
    if st.button("New Chat"):
        st.session_state.messages = []
        st.session_state.chat_id = KaiClient.new_chat_id()
        st.session_state.pending_approval = None
        st.rerun()
    st.caption(f"Chat ID: `{st.session_state.chat_id[:8]}...`")


# --- Helpers ---
def extract_suggestions(text: str) -> tuple[str, list[str]]:
    """Split trailing suggested-action list items from a response.

    Handles multiple formats Kai may use:
      - A fenced code block containing list items at the end
      - Plain markdown list items (- or *) at the end
    Returns (body_without_suggestions, list_of_suggestion_strings).
    """
    stripped = text.rstrip()

    # Try fenced code block with list items at the end:  ```next_actions\n- item\n```
    m = re.search(r'\n```[^\n]*\n((?:\s*[-*]\s+.+\n?)+)\s*```\s*$', stripped)
    if m:
        items_block = m.group(1)
        body = stripped[: m.start()].rstrip()
    else:
        # Try plain trailing list items (- or *)
        m = re.search(r'\n((?:[-*]\s+.+\n?){2,})$', stripped)
        if m:
            items_block = m.group(1)
            body = stripped[: m.start()].rstrip()
        else:
            return text, []

    suggestions = [
        re.sub(r'^\s*[-*]\s+', '', line).strip()
        for line in items_block.strip().splitlines()
        if line.strip()
    ]
    return body, suggestions


def run_async(coro):
    """Run an async coroutine from sync Streamlit code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def get_client() -> KaiClient:
    """Create a KaiClient with auto-discovered URL."""
    return await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=api_url,
    )


async def collect_chat_response(chat_id, text, container):
    """Stream a chat response into a container. Returns (full_text, pending_approval)."""
    accumulated = ""
    pending = None
    tool_names: dict[str, str] = {}  # tool_call_id -> tool_name
    text_placeholder = container.empty()
    client = await get_client()

    async with client:
        async for event in client.send_message(chat_id, text):
            if event.type == "text":
                accumulated += event.text
                text_placeholder.markdown(accumulated + "▌")
            elif event.type == "tool-call":
                call_id = getattr(event, "tool_call_id", "")
                name = getattr(event, "tool_name", None)
                state = getattr(event, "state", None)
                if name:
                    tool_names[call_id] = name
                display_name = name or tool_names.get(call_id, "tool")
                if state == "input-available":
                    # Finalize current text, show tool status, start new text placeholder
                    text_placeholder.markdown(accumulated)
                    container.info(f"Calling **{display_name}**...")
                    text_placeholder = container.empty()
                elif state == "output-available":
                    text_placeholder.markdown(accumulated)
                    container.info(f"**{display_name}** completed.")
                    text_placeholder = container.empty()
            elif event.type == "tool-approval-request":
                pending = {
                    "approval_id": event.approval_id,
                    "tool_call_id": event.tool_call_id,
                }
            elif event.type == "error":
                container.error(getattr(event, "message", "Unknown error"))

    text_placeholder.markdown(accumulated)
    return accumulated, pending


async def collect_approval_response(chat_id, approval_id, approved, placeholder=None):
    """Handle tool approval and stream the continuation. Returns the full text."""
    accumulated = ""
    client = await get_client()

    async with client:
        if approved:
            stream = client.approve_tool(chat_id=chat_id, approval_id=approval_id)
        else:
            stream = client.reject_tool(
                chat_id=chat_id, approval_id=approval_id, reason="User denied"
            )

        async for event in stream:
            if event.type == "text":
                accumulated += event.text
                if placeholder:
                    placeholder.markdown(accumulated + "▌")
            elif event.type == "tool-call":
                tool_name = getattr(event, "tool_name", None) or "unknown"
                if getattr(event, "state", None) == "output-available":
                    st.info(f"**{tool_name}** completed.")
            elif event.type == "error":
                st.error(getattr(event, "message", "Unknown error"))

    if placeholder:
        placeholder.markdown(accumulated)
    return accumulated


# --- Render chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Render suggestion buttons (only for the latest response) ---
if st.session_state.suggestions and not st.session_state.pending_approval:
    cols = st.columns(len(st.session_state.suggestions))
    for i, suggestion in enumerate(st.session_state.suggestions):
        with cols[i]:
            if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                st.session_state.suggestions = []
                st.session_state._pending_prompt = suggestion
                st.rerun()

# --- Handle pending tool approval ---
if st.session_state.pending_approval:
    approval = st.session_state.pending_approval
    st.warning("A tool requires your approval before it can execute.")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Approve", type="primary", use_container_width=True):
            st.session_state.pending_approval = None
            with st.chat_message("assistant"):
                placeholder = st.empty()
                result = run_async(
                    collect_approval_response(
                        st.session_state.chat_id,
                        approval["approval_id"],
                        True,
                        placeholder=placeholder,
                    )
                )
            st.session_state.messages.append({"role": "assistant", "content": result})
            st.rerun()

    with col2:
        if st.button("Deny", use_container_width=True):
            st.session_state.pending_approval = None
            result = run_async(
                collect_approval_response(
                    st.session_state.chat_id,
                    approval["approval_id"],
                    False,
                )
            )
            if result:
                st.session_state.messages.append({"role": "assistant", "content": result})
            st.rerun()

# --- Chat input ---
# Accept input from chat box or from a suggestion button click
prompt = st.chat_input("Ask Kai anything about your Keboola project...")
if st.session_state.get("_pending_prompt"):
    prompt = st.session_state.pop("_pending_prompt")

if prompt:
    # Clear previous suggestions
    st.session_state.suggestions = []
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        container = st.container()
        result_text, pending = run_async(
            collect_chat_response(st.session_state.chat_id, prompt, container)
        )

    # Extract suggestions from the response
    body, suggestions = extract_suggestions(result_text)
    st.session_state.messages.append({"role": "assistant", "content": body})
    st.session_state.suggestions = suggestions

    if pending:
        st.session_state.pending_approval = pending

    st.rerun()

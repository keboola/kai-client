"""
Bare-bones Streamlit data app that integrates with Kai through the KaiClient.

Run with:
    streamlit run examples/streamlit_app.py

Requires:
    pip install streamlit  (or: uv pip install streamlit)

Credentials are loaded from a .env.local file in the project root:
    STORAGE_API_TOKEN=your-keboola-token
    STORAGE_API_URL=https://connection.keboola.com

In a Keboola Data App deployed with Kai, KAI_STORAGE_API_TOKEN, KAI_ENABLED, KBC_URL
and WORKSPACE_ID are injected for you; resolve_storage_api_token() prefers the Kai token.

Tool approvals are not supported in this example:
  - kai-client asks kai-agent to announce a waiting tool (a write tool, a question to the
    user or a plan card) with a tool-approval-request event, and the stream stays open
    until submit_approval() answers it.
  - Streamlit reruns the script on every button click, which ends the stream, so the app
    cannot wait for the user's decision.
  - The app therefore denies every request as soon as it appears, and Kai continues
    without that tool. Deploy the app with a direct-grant input mapping (strict mode),
    where Kai has no write tools.
"""

import asyncio
import os
import re
from contextlib import aclosing
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from kai_client import (
    KaiClient,
    KaiConfigurationError,
    KaiError,
    KaiNotFoundError,
    resolve_storage_api_token,
)

# Load credentials from .env.local (same as the kai CLI)
_env_local = Path(__file__).resolve().parent.parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)

st.set_page_config(page_title="Kai Chat", page_icon="🤖", layout="wide")
st.title("Kai Chat")

# KAI_STORAGE_API_TOKEN first, then STORAGE_API_TOKEN; never KBC_TOKEN, which kai-agent refuses.
try:
    token = resolve_storage_api_token() or ""
except KaiConfigurationError as e:
    st.error(f"Kai is not available in this run of the app. {e.message}")
    st.stop()
api_url = os.environ.get("STORAGE_API_URL") or os.environ.get("KBC_URL", "")
# Injected automatically into every Data App container by Keboola — pins Kai's queries to
# this app's own workspace. Required with the Kai token; unset outside a Data App.
workspace_id = os.environ.get("WORKSPACE_ID") or None

if os.environ.get("KAI_STORAGE_API_TOKEN") and not workspace_id:
    st.error(
        "Kai is not available: KAI_STORAGE_API_TOKEN needs WORKSPACE_ID. "
        "Enable the app's workspace and redeploy it."
    )
    st.stop()

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
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []

with st.sidebar:
    st.header("Kai Chat")
    if st.button("New Chat"):
        st.session_state.messages = []
        st.session_state.chat_id = KaiClient.new_chat_id()
        st.rerun()
    st.caption(f"Chat ID: `{st.session_state.chat_id[:8]}...`")
    st.caption(
        "Write actions and questions need an answer this example cannot collect; "
        "it declines them."
    )


DENY_REASON = "This app cannot show approvals or questions to the user. Continue without them."


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
    """Create a KaiClient for the auto-discovered kai-agent backend."""
    return await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=api_url,
        workspace_id=workspace_id,
    )


async def deny_approval(client: KaiClient, chat_id: str, tool_call_id: str) -> None:
    """Deny a waiting tool; retry once on 404, as kai-agent already waits 10 s before it."""
    try:
        await client.submit_approval(
            chat_id=chat_id, tool_use_id=tool_call_id, approved=False, reason=DENY_REASON
        )
    except KaiNotFoundError:
        await client.submit_approval(
            chat_id=chat_id, tool_use_id=tool_call_id, approved=False, reason=DENY_REASON
        )


async def collect_chat_response(chat_id, text, container):
    """Stream a chat response into a container. Returns the full text."""
    accumulated = ""
    tool_names: dict[str, str] = {}  # tool_call_id -> tool_name
    text_placeholder = container.empty()
    client = await get_client()

    # aclosing() closes the stream when this function returns early.
    async with client, aclosing(client.send_message(chat_id, text)) as events:
        async for event in events:
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
                display_name = tool_names.get(event.tool_call_id, "tool")
                try:
                    await deny_approval(client, chat_id, event.tool_call_id)
                    container.info(f"Declined **{display_name}**: this app cannot ask you.")
                except KaiError as e:
                    # A conflict (409) means the request is already resolved, so Kai goes on.
                    code = e.code or ""
                    if not (code.startswith("conflict") or code == "http:409"):
                        # Still waiting: the turn stays blocked until kai-agent times it out.
                        text_placeholder.markdown(accumulated)
                        container.error(
                            f"Could not decline **{display_name}**, so Kai cannot go on: "
                            f"{e.message}"
                        )
                        return accumulated
            elif event.type == "tool-output-error":
                display_name = tool_names.get(event.tool_call_id, "tool")
                text_placeholder.markdown(accumulated)
                container.warning(f"**{display_name}** failed: {event.error_text}")
                text_placeholder = container.empty()
            elif event.type == "error":
                container.error(f"Kai could not finish this answer: {event.message}")

    text_placeholder.markdown(accumulated)
    return accumulated


# --- Render chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Render suggestion buttons (only for the latest response) ---
if st.session_state.suggestions:
    cols = st.columns(len(st.session_state.suggestions))
    for i, suggestion in enumerate(st.session_state.suggestions):
        with cols[i]:
            if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                st.session_state.suggestions = []
                st.session_state._pending_prompt = suggestion
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
        result_text = run_async(collect_chat_response(st.session_state.chat_id, prompt, container))

    # Extract suggestions from the response
    body, suggestions = extract_suggestions(result_text)
    st.session_state.messages.append({"role": "assistant", "content": body})
    st.session_state.suggestions = suggestions

    st.rerun()

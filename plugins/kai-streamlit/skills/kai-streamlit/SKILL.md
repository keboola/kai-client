---
name: Kai Streamlit Integration Guide
description: This skill should be used when the user asks to "build a streamlit app with Kai", "create a Keboola data app", "integrate Kai with Streamlit", "stream Kai responses in Streamlit", "add Kai chat to Streamlit", "build a Keboola chat UI", "create a data app", or mentions Streamlit with Kai, KaiClient, or Keboola AI Assistant. Provides patterns, gotchas, and working code for building Streamlit apps that integrate with the KaiClient library.
version: 1.0.0
---

# Building Streamlit Data Apps with Kai

This guide covers the patterns, pitfalls, and working solutions for integrating the KaiClient Python library into Streamlit data apps.

## Prerequisites

### Dependencies

```bash
pip install kai-client streamlit python-dotenv
```

### Credentials

Kai requires two environment variables. Load them from a `.env.local` file — never put credential inputs in the app UI:

```python
from pathlib import Path
from dotenv import load_dotenv

_env_local = Path(__file__).resolve().parent.parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)
```

`.env.local`:
```
STORAGE_API_TOKEN=your-keboola-token
STORAGE_API_URL=https://connection.keboola.com
```

Show a clear error if credentials are missing:
```python
token = os.environ.get("STORAGE_API_TOKEN", "")
api_url = os.environ.get("STORAGE_API_URL", "")

if not token or not api_url:
    st.error("Missing credentials. Create a `.env.local` file...")
    st.stop()
```

## Critical Patterns

### 1. Async Bridge

KaiClient is fully async. Streamlit is sync. Bridge with a dedicated event loop per call:

```python
def run_async(coro):
    """Run an async coroutine from sync Streamlit code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
```

> **Why `asyncio.new_event_loop()`?** Streamlit may have its own event loop. Creating a fresh one avoids conflicts.

### 2. Client Creation — Always Use `from_storage_api()`

The `KaiClient()` constructor defaults `base_url` to `http://localhost:3000`. For production, you **must** use the async factory method which auto-discovers the real kai-assistant URL:

```python
async def get_client() -> KaiClient:
    return await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=api_url,
    )
```

> **Gotcha:** Using `KaiClient(token, url)` directly causes `httpx.RemoteProtocolError: illegal request line` because it sends requests to localhost.

### 3. Streaming into Containers (Inline Tool Calls)

Use `st.container()` with dynamic `st.empty()` placeholders — not a single `st.empty()`. This lets tool call indicators appear inline between text chunks instead of always at the bottom:

```python
async def collect_chat_response(chat_id, text, container):
    accumulated = ""
    tool_names: dict[str, str] = {}  # tool_call_id -> name
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
                    text_placeholder.markdown(accumulated)
                    container.info(f"Calling **{display_name}**...")
                    text_placeholder = container.empty()
                elif state == "output-available":
                    text_placeholder.markdown(accumulated)
                    container.info(f"**{display_name}** completed.")
                    text_placeholder = container.empty()

    text_placeholder.markdown(accumulated)
    return accumulated
```

Call it like:
```python
with st.chat_message("assistant"):
    container = st.container()
    result_text = run_async(collect_chat_response(chat_id, prompt, container))
```

> **Why track `tool_names`?** The `output-available` event often has `tool_name=None`. Cache the name from the `input-available` event using the `tool_call_id` as the key.

### 4. Session State

Streamlit re-runs the entire script on every interaction. Store all chat state in `st.session_state`:

```python
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_id" not in st.session_state:
    st.session_state.chat_id = KaiClient.new_chat_id()
if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []
```

### 5. No `nonlocal` in Streamlit Scripts

Python's `nonlocal` only works with enclosing **function** scopes, not block scopes. Since Streamlit scripts execute at module level inside `if` blocks, defining an `async def` inside an `if` block and using `nonlocal` causes a `SyntaxError`:

```python
# BROKEN — SyntaxError: no binding for nonlocal 'accumulated' found
if prompt:
    accumulated = ""
    async def do_chat():
        nonlocal accumulated  # ERROR!
        ...
```

**Fix:** Extract async logic into standalone functions that take parameters and return results:

```python
async def collect_chat_response(chat_id, text, container):
    accumulated = ""
    # ... (all logic here)
    return accumulated
```

## Tool Approval Flow

When Kai calls a write tool, the stream pauses with a `tool-approval-request` event. Handle it with Approve/Deny buttons:

```python
# During streaming — capture the pending approval
elif event.type == "tool-approval-request":
    pending = {
        "approval_id": event.approval_id,
        "tool_call_id": event.tool_call_id,
    }

# Store in session state
if pending:
    st.session_state.pending_approval = pending
    st.rerun()
```

Render approval UI:
```python
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
```

The approval handler:
```python
async def collect_approval_response(chat_id, approval_id, approved, placeholder=None):
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

    if placeholder:
        placeholder.markdown(accumulated)
    return accumulated
```

## Suggested Actions as Buttons

Kai returns suggested next actions in a fenced code block with a `next_actions` tag:

```
\`\`\`next_actions
- Explore tables in a specific bucket
- Search for a configuration by name
\`\`\`
```

Extract them and render as clickable buttons:

```python
import re

def extract_suggestions(text: str) -> tuple[str, list[str]]:
    stripped = text.rstrip()

    # Fenced code block: ```next_actions\n- item\n```
    m = re.search(r'\n```[^\n]*\n((?:\s*[-*]\s+.+\n?)+)\s*```\s*$', stripped)
    if m:
        items_block = m.group(1)
        body = stripped[: m.start()].rstrip()
    else:
        # Plain trailing list items
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
```

> **Key insight:** The code block tag is `next_actions`, not plain ` ``` `. Use `[^\n]*` after the opening backticks to match any tag.

Render buttons and wire them to send as the next message:

```python
if st.session_state.suggestions:
    cols = st.columns(len(st.session_state.suggestions))
    for i, suggestion in enumerate(st.session_state.suggestions):
        with cols[i]:
            if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                st.session_state.suggestions = []
                st.session_state._pending_prompt = suggestion
                st.rerun()
```

In the chat input section, check for button-triggered prompts:
```python
prompt = st.chat_input("Ask Kai anything...")
if st.session_state.get("_pending_prompt"):
    prompt = st.session_state.pop("_pending_prompt")
```

> **Gotcha:** Don't append to `messages` in both the button handler AND the prompt handler — this causes duplicate messages. Only append in one place (the prompt handler).

## SSE Event Reference

See `references/sse-events.md` for all event types.

Key events for Streamlit integration:

| Event Type | Use In Streamlit |
|------------|-----------------|
| `text` | Append to `accumulated`, update `placeholder.markdown()` |
| `tool-call` (state: `input-available`) | Show `container.info("Calling tool...")` |
| `tool-call` (state: `output-available`) | Show `container.info("tool completed.")` |
| `tool-approval-request` | Store in `st.session_state.pending_approval` |
| `error` | Show `container.error(event.message)` |

## Reference Example

A complete working Streamlit app is available at `examples/streamlit_app.py` in the kai-client repository.

## Additional Resources

- **`references/streamlit-patterns.md`** — Streamlit-specific async patterns and component tips
- **`references/sse-events.md`** — Full SSE event type reference

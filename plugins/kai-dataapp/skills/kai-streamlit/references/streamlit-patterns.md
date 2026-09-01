# Streamlit + KaiClient Patterns

## App Architecture

A Kai-integrated Streamlit app follows this structure:

```
1. Load credentials from .env.local
2. Initialize session state (messages, chat_id, pending_approval, suggestions)
3. Render sidebar (New Chat button, chat ID display)
4. Render chat history from session state
5. Render suggestion buttons (if any)
6. Render tool approval UI (if pending)
7. Handle chat input (from text box or suggestion button)
8. Stream response, extract suggestions, update session state
9. st.rerun() to render the new state
```

## Async Pattern

KaiClient is async; Streamlit is sync. Always use a fresh event loop:

```python
def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
```

Never use `asyncio.run()` inside Streamlit — it may conflict with Streamlit's internal loop.

## Streaming Text with Cursor

Show a blinking cursor during streaming by appending `"▌"`:

```python
text_placeholder.markdown(accumulated + "▌")
```

Remove it when streaming completes:
```python
text_placeholder.markdown(accumulated)
```

## Inline Tool Call Indicators

Use `st.container()` + dynamic `st.empty()` to show tool calls between text:

```python
container = st.container()
text_placeholder = container.empty()

# When a tool call arrives:
text_placeholder.markdown(accumulated)          # Finalize current text
container.info(f"Calling **{tool_name}**...")    # Tool indicator in order
text_placeholder = container.empty()             # New placeholder for next text
```

This ensures tool indicators appear at the point they were called, not at the bottom.

## Avoiding Duplicate Messages

When suggestion buttons trigger a chat, only append to `messages` in one place:

```python
# Button handler — only sets the pending prompt, does NOT append to messages
if st.button(suggestion):
    st.session_state._pending_prompt = suggestion
    st.rerun()

# Prompt handler — the single place that appends
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
```

## Chat History Rendering

Always render from session state to survive reruns:

```python
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
```

## New Chat Reset

Reset all relevant state:

```python
if st.button("New Chat"):
    st.session_state.messages = []
    st.session_state.chat_id = KaiClient.new_chat_id()
    st.session_state.pending_approval = None
    st.session_state.suggestions = []
    st.rerun()
```

## Error Display

Use `st.error()` inside the streaming container for inline errors:

```python
elif event.type == "error":
    container.error(getattr(event, "message", "Unknown error"))
```

## Debugging Tip

`st.expander()` and `st.write()` inside the prompt handler won't survive `st.rerun()`. To debug response text, write to a file:

```python
from pathlib import Path
Path("/tmp/kai_debug.txt").write_text(repr(result_text))
```

Then inspect with `cat /tmp/kai_debug.txt`.

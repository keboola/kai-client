/**
 * Kai Data App - Frontend
 *
 * Pure vanilla JS chat client that:
 * - Sends messages to the Express backend (which proxies to kai-assistant)
 * - Parses SSE streams for text, tool calls, tool approvals, and errors
 * - Renders markdown-ish text with code blocks
 * - Handles tool approval flow
 * - Extracts and renders suggestion buttons
 */

const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat");
const approvalBar = document.getElementById("approval-bar");
const approveBtn = document.getElementById("approve-btn");
const denyBtn = document.getElementById("deny-btn");
const suggestionsEl = document.getElementById("suggestions");

let chatId = crypto.randomUUID();
let pendingApproval = null;
let isStreaming = false;

// ── Helpers ──

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setStreaming(val) {
  isStreaming = val;
  sendBtn.disabled = val;
  chatInput.disabled = val;
}

/**
 * Minimal markdown rendering: code blocks, inline code, bold, links.
 */
function renderMarkdown(text) {
  return text
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
      return `<pre><code class="language-${lang}">${escapeHtml(code.trim())}</code></pre>`;
    })
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\n/g, "<br>");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Parse list items from a block of text (lines starting with - or *).
 */
function parseListItems(block) {
  return block
    .trim()
    .split("\n")
    .map((line) => line.replace(/^\s*[-*]\s+/, "").trim())
    .filter(Boolean);
}

/**
 * Extract suggestion items from the end of a response.
 * Handles ```next_actions blocks and trailing list items.
 */
function extractSuggestions(text) {
  const stripped = text.trimEnd();

  // Try fenced code block with list items
  const fencedMatch = stripped.match(/\n```[^\n]*\n((?:\s*[-*]\s+.+\n?)+)\s*```\s*$/);
  if (fencedMatch) {
    return {
      body: stripped.slice(0, fencedMatch.index).trimEnd(),
      suggestions: parseListItems(fencedMatch[1]),
    };
  }

  // Try plain trailing list items (need at least 2)
  const listMatch = stripped.match(/\n((?:[-*]\s+.+\n?){2,})$/);
  if (listMatch) {
    return {
      body: stripped.slice(0, listMatch.index).trimEnd(),
      suggestions: parseListItems(listMatch[1]),
    };
  }

  return { body: text, suggestions: [] };
}

// ── Message rendering ──

function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "message user";
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function createAssistantMessage() {
  const div = document.createElement("div");
  div.className = "message assistant";
  const content = document.createElement("div");
  content.className = "markdown-content";
  div.appendChild(content);
  messagesEl.appendChild(div);
  return { container: div, content };
}

function addToolIndicator(container, text, completed = false) {
  const div = document.createElement("div");
  div.className = "tool-indicator" + (completed ? " completed" : "");
  div.textContent = text;
  container.appendChild(div);
  scrollToBottom();
}

function addError(text) {
  const div = document.createElement("div");
  div.className = "error-msg";
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function renderSuggestions(suggestions) {
  suggestionsEl.innerHTML = "";
  for (const text of suggestions) {
    const btn = document.createElement("button");
    btn.className = "suggestion-btn";
    btn.textContent = text;
    btn.addEventListener("click", () => {
      suggestionsEl.innerHTML = "";
      sendMessage(text);
    });
    suggestionsEl.appendChild(btn);
  }
}

// ── SSE Parsing ──

/**
 * Parse SSE data lines from a text chunk.
 * Kai SSE format: "data: {json}\n\n" -- no "event:" lines, type is inside JSON.
 */
function* parseSSEChunk(text) {
  for (const line of text.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const raw = line.slice(5).trim();
    if (raw === "[DONE]") {
      yield { type: "done", data: null };
      continue;
    }
    try {
      const data = JSON.parse(raw);
      yield { type: data.type || "unknown", data };
    } catch {
      // skip unparseable lines
    }
  }
}

// ── SSE stream reader ──

/**
 * Read an SSE response stream and invoke a callback for each parsed event.
 * Returns the response object, or null if the fetch failed (error already shown).
 */
async function readSSEStream(url, fetchOptions, onEvent) {
  const res = await fetch(url, fetchOptions);

  if (!res.ok) {
    const err = await res.text();
    addError(`Error: ${err}`);
    return null;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let sseBuffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    sseBuffer += decoder.decode(value, { stream: true });

    // Process complete SSE messages (double newline separated)
    const parts = sseBuffer.split("\n\n");
    sseBuffer = parts.pop(); // Keep incomplete part in buffer

    for (const part of parts) {
      if (!part.trim()) continue;
      for (const event of parseSSEChunk(part + "\n\n")) {
        onEvent(event);
      }
    }
  }

  return res;
}

// ── Core chat logic ──

async function sendMessage(text) {
  if (!text.trim() || isStreaming) return;

  suggestionsEl.innerHTML = "";
  addUserMessage(text);
  setStreaming(true);

  const { container, content } = createAssistantMessage();
  let accumulated = "";
  const toolNames = {};

  const payload = {
    id: chatId,
    message: {
      id: crypto.randomUUID(),
      role: "user",
      parts: [{ type: "text", text }],
    },
    selectedChatModel: "chat-model",
    selectedVisibilityType: "private",
  };

  try {
    const res = await readSSEStream(
      "/api/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      ({ type, data }) => {
        switch (type) {
          case "text-delta":
            if (data && data.delta) {
              accumulated += data.delta;
              content.innerHTML = renderMarkdown(accumulated) + '<span class="cursor"></span>';
              scrollToBottom();
            }
            break;

          case "tool-call": {
            const callId = data.toolCallId || "";
            const name = data.toolName || null;
            const state = data.state || "";

            if (name) toolNames[callId] = name;
            const displayName = name || toolNames[callId] || "tool";

            if (state === "input-available") {
              content.innerHTML = renderMarkdown(accumulated);
              addToolIndicator(container, `Calling ${displayName}...`);
            } else if (state === "output-available") {
              addToolIndicator(container, `${displayName} completed.`, true);
            }
            break;
          }

          case "tool-approval-request":
            pendingApproval = {
              approvalId: data.approvalId,
              toolCallId: data.toolCallId,
            };
            approvalBar.classList.remove("hidden");
            break;

          case "error":
            addError(data.message || "Unknown error");
            break;
        }
      }
    );

    if (!res) {
      container.remove();
    } else if (accumulated) {
      content.innerHTML = renderMarkdown(accumulated);
      const { body, suggestions } = extractSuggestions(accumulated);
      if (suggestions.length > 0) {
        content.innerHTML = renderMarkdown(body);
        renderSuggestions(suggestions);
      }
    } else {
      container.remove();
    }
  } catch (err) {
    container.remove();
    addError(`Connection error: ${err.message}`);
  }

  setStreaming(false);
  chatInput.focus();
}

async function handleApproval(approved) {
  if (!pendingApproval) return;

  approvalBar.classList.add("hidden");
  const { approvalId } = pendingApproval;
  pendingApproval = null;

  setStreaming(true);
  const { container, content } = createAssistantMessage();
  let accumulated = "";
  const toolNames = {};

  const action = approved ? "approve" : "reject";
  const endpoint = `/api/chat/${chatId}/${action}/${approvalId}`;

  try {
    const res = await readSSEStream(
      endpoint,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
      ({ type, data }) => {
        if (type === "text-delta" && data && data.delta) {
          accumulated += data.delta;
          content.innerHTML = renderMarkdown(accumulated) + '<span class="cursor"></span>';
          scrollToBottom();
        } else if (type === "tool-call") {
          const callId = data.toolCallId || "";
          const name = data.toolName || null;
          const state = data.state || "";
          if (name) toolNames[callId] = name;
          const displayName = name || toolNames[callId] || "tool";
          if (state === "input-available") {
            content.innerHTML = renderMarkdown(accumulated);
            addToolIndicator(container, `Calling ${displayName}...`);
          } else if (state === "output-available") {
            addToolIndicator(container, `${displayName} completed.`, true);
          }
        } else if (type === "error") {
          addError(data.message || "Unknown error");
        }
      }
    );

    if (res) {
      content.innerHTML = renderMarkdown(accumulated);
    }
  } catch (err) {
    addError(`Connection error: ${err.message}`);
  }

  setStreaming(false);
}

// ── Event listeners ──

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (text) {
    chatInput.value = "";
    sendMessage(text);
  }
});

newChatBtn.addEventListener("click", () => {
  chatId = crypto.randomUUID();
  messagesEl.innerHTML = "";
  suggestionsEl.innerHTML = "";
  approvalBar.classList.add("hidden");
  pendingApproval = null;
  chatInput.focus();
});

approveBtn.addEventListener("click", () => handleApproval(true));
denyBtn.addEventListener("click", () => handleApproval(false));

// Check credentials on load
fetch("/api/config")
  .then((r) => r.json())
  .then((config) => {
    if (!config.hasCredentials) {
      addError(
        "Missing credentials. Set STORAGE_API_TOKEN and STORAGE_API_URL in .env.local (local) or as environment variables (Keboola)."
      );
    }
  });

chatInput.focus();

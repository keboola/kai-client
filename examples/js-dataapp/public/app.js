/**
 * Kai Data App - Frontend
 *
 * Pure vanilla JS chat client that:
 * - Sends messages to the Express backend (which proxies to kai-agent)
 * - Parses SSE streams for text, tool calls, tool approvals, and errors
 * - Renders markdown-ish text with code blocks
 * - Handles tool approval flow (the chat stream stays open while a tool waits)
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
const approvalTextEl = document.getElementById("approval-text");

let chatId = crypto.randomUUID();
// Tools waiting for a decision, oldest first: { chatId, toolCallId, toolName }
let pendingApprovals = [];
let isStreaming = false;
let kaiUnavailable = false;
let streamAbort = null;

// ── Helpers ──

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setStreaming(val) {
  isStreaming = val;
  sendBtn.disabled = val || kaiUnavailable;
  chatInput.disabled = val || kaiUnavailable;
}

function showNextApproval() {
  const next = pendingApprovals[0];
  if (!next) {
    approvalBar.classList.add("hidden");
    return;
  }
  approvalTextEl.textContent = `Kai wants to run ${next.toolName}. Approve it?`;
  approveBtn.disabled = false;
  denyBtn.disabled = false;
  approvalBar.classList.remove("hidden");
}

function clearApprovals() {
  pendingApprovals = [];
  showNextApproval();
}

/**
 * Remove a tool's card once its outcome arrives, e.g. after kai-agent denied it on timeout.
 */
function dropApproval(toolCallId) {
  const wasFirst = pendingApprovals[0] && pendingApprovals[0].toolCallId === toolCallId;
  pendingApprovals = pendingApprovals.filter((a) => a.toolCallId !== toolCallId);
  if (wasFirst) showNextApproval();
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
    addError(`Error: ${await readErrorMessage(res)}`);
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

  const turnChatId = chatId;
  streamAbort = new AbortController();
  let finished = false;
  const payload = { id: turnChatId, text };

  try {
    const res = await readSSEStream(
      "/api/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: streamAbort.signal,
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

          case "tool-input-start":
            toolNames[data.toolCallId] = data.toolName;
            break;

          case "tool-input-available": {
            const name = data.toolName || toolNames[data.toolCallId] || "tool";
            toolNames[data.toolCallId] = name;
            content.innerHTML = renderMarkdown(accumulated);
            addToolIndicator(container, `Calling ${name}...`);
            break;
          }

          case "tool-output-available":
            dropApproval(data.toolCallId);
            addToolIndicator(container, `${toolNames[data.toolCallId] || "tool"} completed.`, true);
            break;

          case "tool-output-error":
            dropApproval(data.toolCallId);
            addToolIndicator(container, `${toolNames[data.toolCallId] || "tool"} failed: ${data.errorText}`);
            break;

          case "tool-approval-request":
            pendingApprovals.push({
              chatId: turnChatId,
              toolCallId: data.toolCallId,
              toolName: toolNames[data.toolCallId] || "a tool",
            });
            if (pendingApprovals.length === 1) showNextApproval();
            break;

          case "error":
            addError(data.errorText || "Kai could not finish this answer.");
            break;

          case "finish":
            finished = true;
            break;
        }
      }
    );

    if (res && !finished) {
      addError("The connection to Kai was lost. The answer may still be running; start a new chat to stop it.");
    }

    if (!res) {
      container.remove();
    } else if (accumulated) {
      content.innerHTML = renderMarkdown(accumulated);
      const { body, suggestions } = extractSuggestions(accumulated);
      if (suggestions.length > 0) {
        content.innerHTML = renderMarkdown(body);
        renderSuggestions(suggestions);
      }
    } else if (!container.querySelector(".tool-indicator")) {
      container.remove();
    }
  } catch (err) {
    container.remove();
    if (err.name !== "AbortError") addError(`Connection error: ${err.message}`);
  }

  // The turn is over, so any decision still pending can no longer apply.
  if (chatId === turnChatId) clearApprovals();
  setStreaming(false);
  chatInput.focus();
}

/**
 * Send the decision for the oldest waiting tool. The chat stream from sendMessage is
 * still open and carries the outcome; this request returns only an acknowledgement.
 */
async function handleApproval(approved) {
  const approval = pendingApprovals[0];
  if (!approval) return;

  approveBtn.disabled = true;
  denyBtn.disabled = true;

  try {
    const res = await fetch(`/api/chat/${approval.chatId}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        toolUseId: approval.toolCallId,
        approved,
        ...(approved ? {} : { reason: "User denied" }),
      }),
    });

    if (res.ok || res.status === 409) {
      // 409: already resolved, timed out or the chat was stopped; retrying cannot help.
      if (res.status === 409 && approval.chatId === chatId) addError(await readErrorMessage(res));
      dropApproval(approval.toolCallId);
      return;
    }
    if (!pendingApprovals.includes(approval)) return;
    addError(`Approval failed: ${await readErrorMessage(res)}`);
  } catch (err) {
    addError(`Connection error: ${err.message}`);
  }
  // Leave the card up so the user can try again.
  approveBtn.disabled = false;
  denyBtn.disabled = false;
}

/**
 * The human-readable message of an error response from the backend or kai-agent.
 */
async function readErrorMessage(res) {
  const text = await res.text();
  try {
    const { error } = JSON.parse(text);
    try {
      const upstream = JSON.parse(error);
      return (upstream.error && upstream.error.message) || upstream.message || error;
    } catch {
      return error;
    }
  } catch {
    return text || `${res.status} ${res.statusText}`;
  }
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
  if (isStreaming) {
    // Closing the stream does not stop the turn on kai-agent.
    fetch(`/api/chat/${chatId}/stop`, { method: "POST" }).catch((err) =>
      console.error("Stop failed:", err)
    );
  }
  if (streamAbort) streamAbort.abort();
  chatId = crypto.randomUUID();
  messagesEl.innerHTML = "";
  suggestionsEl.innerHTML = "";
  clearApprovals();
  chatInput.focus();
});

approveBtn.addEventListener("click", () => handleApproval(true));
denyBtn.addEventListener("click", () => handleApproval(false));

// Check whether Kai can be used in this run on load
fetch("/api/config")
  .then((r) => r.json())
  .then((config) => {
    if (config.kaiError) {
      kaiUnavailable = true;
      setStreaming(isStreaming);
      addError(config.kaiError);
    }
  })
  .catch((err) => addError(`Could not load the app configuration: ${err.message}`));

chatInput.focus();

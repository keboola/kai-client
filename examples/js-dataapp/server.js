/**
 * Kai Data App - Express backend
 *
 * Handles:
 * - Service discovery (finds the kai-agent URL from Keboola Storage API)
 * - Proxies chat requests and tool approvals with proper auth headers
 * - Serves the static frontend
 *
 * Credentials come from environment variables (Keboola injects these in production)
 * or from .env.local for local development.
 */

require("dotenv").config({ path: ".env.local" });

const { randomUUID } = require("crypto");
const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static("public"));

const STORAGE_API_URL = process.env.STORAGE_API_URL || process.env.KBC_URL || "";
// Injected automatically into every Data App container by Keboola — pins Kai's queries to
// this app's own workspace. Required with the Kai token; empty outside a Data App.
const WORKSPACE_ID = process.env.WORKSPACE_ID || "";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// kai-agent already waits 10 s for an approval slot before answering 404, so retry once.
const APPROVAL_ATTEMPTS = 2;
// Questions and plan cards wait for the user indefinitely and need a richer UI than Approve/Deny.
const DISALLOWED_TOOLS = ["AskUserQuestion", "ExitPlanMode"];

function isKaiEnabled() {
  const value = (process.env.KAI_ENABLED || "").trim().toLowerCase();
  return !["", "0", "false", "no", "off"].includes(value);
}

/**
 * Resolve the token Kai authenticates with.
 *
 * 1. KAI_STORAGE_API_TOKEN — the Kai token Keboola injects into apps deployed with Kai.
 * 2. KAI_ENABLED without the Kai token — Kai is unavailable; never fall back to another token.
 * 3. Otherwise STORAGE_API_TOKEN — a project member's personal token (local dev, apps without Kai).
 *
 * KBC_TOKEN is never used: it has no Keboola user, and kai-agent refuses it with 403.
 */
function resolveKaiToken() {
  const kaiToken = process.env.KAI_STORAGE_API_TOKEN || "";
  if (kaiToken) {
    if (!WORKSPACE_ID) {
      return {
        token: "",
        error:
          "Kai is not available: KAI_STORAGE_API_TOKEN needs WORKSPACE_ID. " +
          "Enable the app's workspace and redeploy it.",
      };
    }
    return { token: kaiToken, error: null };
  }
  if (isKaiEnabled()) {
    return {
      token: "",
      error:
        "Kai is not available in this run of the app: KAI_ENABLED is set but " +
        "KAI_STORAGE_API_TOKEN is missing. Redeploy the app as a user who is allowed " +
        "to create Storage API tokens.",
    };
  }
  return { token: process.env.STORAGE_API_TOKEN || "", error: null };
}

const { token: KAI_TOKEN, error: KAI_CONFIG_ERROR } = resolveKaiToken();

function kaiHeaders() {
  return {
    "Content-Type": "application/json",
    "x-storageapi-token": KAI_TOKEN,
    "x-storageapi-url": STORAGE_API_URL,
    ...(WORKSPACE_ID && { "x-workspace-id": WORKSPACE_ID }),
  };
}

/**
 * The reason Kai cannot be called in this run, or null when it can.
 */
function kaiUnavailableReason() {
  if (KAI_CONFIG_ERROR) return KAI_CONFIG_ERROR;
  if (!KAI_TOKEN || !STORAGE_API_URL) {
    return "Missing credentials: set STORAGE_API_TOKEN (KBC_TOKEN does not work with Kai) and STORAGE_API_URL.";
  }
  return null;
}

let _kaiBaseUrl = null;

/**
 * Discover the kai-agent service URL from Keboola Storage API.
 */
async function discoverKaiUrl() {
  if (_kaiBaseUrl) return _kaiBaseUrl;

  const res = await fetch(`${STORAGE_API_URL.replace(/\/$/, "")}/v2/storage`, {
    headers: { "x-storageapi-token": KAI_TOKEN },
  });

  if (!res.ok) {
    throw new Error(`Storage API discovery failed: ${res.status} ${res.statusText}`);
  }

  const data = await res.json();
  const kaiService = (data.services || []).find((s) => s.id === "kai-agent");

  if (!kaiService || !kaiService.url) {
    const available = (data.services || []).map((s) => s.id);
    throw new Error(`kai-agent service not found. Available: ${available.join(", ")}`);
  }

  _kaiBaseUrl = kaiService.url.replace(/\/$/, "");
  console.log(`Discovered kai-agent at: ${_kaiBaseUrl}`);
  return _kaiBaseUrl;
}

/**
 * Forward a chat turn to kai-agent and stream the SSE response back.
 * The stream stays open while a tool waits for approval.
 */
async function proxySSE(payload, res) {
  const kaiUrl = await discoverKaiUrl();
  const abort = new AbortController();
  res.on("close", () => abort.abort());

  const upstream = await fetch(`${kaiUrl}/api/chat`, {
    method: "POST",
    headers: kaiHeaders(),
    body: JSON.stringify(payload),
    signal: abort.signal,
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    return res.status(upstream.status).json({ error: text });
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    res.write(decoder.decode(value, { stream: true }));
  }

  res.end();
}

/**
 * POST a tool decision to kai-agent.
 * - 404: the approval slot is not registered yet, so retry.
 * - 409: the decision can no longer apply (resolved, timed out, chat stopped); final.
 */
async function postApproval(chatId, decision, signal) {
  const kaiUrl = await discoverKaiUrl();
  let upstream;
  for (let attempt = 1; attempt <= APPROVAL_ATTEMPTS; attempt++) {
    upstream = await fetch(`${kaiUrl}/api/chat/${chatId}/approval`, {
      method: "POST",
      headers: kaiHeaders(),
      body: JSON.stringify(decision),
      signal,
    });
    if (upstream.status !== 404) break;
  }
  return upstream;
}

/**
 * Forward a JSON response from kai-agent, wrapping an error body as { error }.
 */
async function sendUpstreamJson(upstream, res) {
  const text = await upstream.text();
  if (!upstream.ok) {
    return res.status(upstream.status).json({ error: text });
  }
  res.status(upstream.status).type("application/json").send(text);
}

/**
 * GET /api/config
 * Returns non-secret config the frontend needs: whether Kai can be used, and why not.
 */
app.get("/api/config", (_req, res) => {
  const reason = kaiUnavailableReason();
  res.json({
    hasCredentials: !!(KAI_TOKEN && STORAGE_API_URL),
    kaiError: reason,
  });
});

/**
 * POST /api/chat
 * Body: { id: chatId, text }
 * Proxies the turn to kai-agent and streams the SSE response back to the frontend.
 */
app.post("/api/chat", async (req, res) => {
  const reason = kaiUnavailableReason();
  if (reason) return res.status(503).json({ error: reason });

  const { id, text } = req.body || {};
  if (!UUID_RE.test(id || "") || typeof text !== "string" || !text.trim()) {
    return res.status(400).json({ error: "Expected { id: <chat UUID>, text }" });
  }

  try {
    await proxySSE(
      {
        id,
        message: { id: randomUUID(), role: "user", parts: [{ type: "text", text }] },
        selectedVisibilityType: "private",
        supportsApprovalRequestedEvent: true,
        // Applies from the chat's first message on.
        toolRestrictions: { disallowedTools: DISALLOWED_TOOLS },
      },
      res
    );
  } catch (err) {
    console.error("Chat error:", err);
    if (!res.headersSent) {
      res.status(500).json({ error: err.message });
    } else {
      res.end();
    }
  }
});

/**
 * POST /api/chat/:chatId/approval
 * Body: { toolUseId, approved, reason? }
 * Sends the user's decision while the chat stream from /api/chat is still open;
 * the outcome arrives on that stream.
 */
app.post("/api/chat/:chatId/approval", async (req, res) => {
  const reason = kaiUnavailableReason();
  if (reason) return res.status(503).json({ error: reason });

  const { chatId } = req.params;
  const { toolUseId, approved, reason: denyReason } = req.body || {};
  if (!UUID_RE.test(chatId) || typeof toolUseId !== "string" || !toolUseId || typeof approved !== "boolean") {
    return res.status(400).json({ error: "Expected { toolUseId, approved } for a chat UUID" });
  }

  const abort = new AbortController();
  res.on("close", () => abort.abort());
  try {
    const upstream = await postApproval(
      chatId,
      {
        toolUseId,
        approved,
        ...(!approved && typeof denyReason === "string" && denyReason && { reason: denyReason }),
      },
      abort.signal
    );
    await sendUpstreamJson(upstream, res);
  } catch (err) {
    console.error("Approval error:", err);
    if (!res.headersSent) res.status(500).json({ error: err.message });
  }
});

/**
 * POST /api/chat/:chatId/stop
 * Stops the chat's running turn; closing the chat stream alone does not stop it.
 */
app.post("/api/chat/:chatId/stop", async (req, res) => {
  const reason = kaiUnavailableReason();
  if (reason) return res.status(503).json({ error: reason });

  const { chatId } = req.params;
  if (!UUID_RE.test(chatId)) return res.status(400).json({ error: "Expected a chat UUID" });

  try {
    const kaiUrl = await discoverKaiUrl();
    const upstream = await fetch(`${kaiUrl}/api/chat/${chatId}/stop`, {
      method: "POST",
      headers: kaiHeaders(),
    });
    await sendUpstreamJson(upstream, res);
  } catch (err) {
    console.error("Stop error:", err);
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Kai Data App running at http://localhost:${PORT}`);
  const reason = kaiUnavailableReason();
  if (reason) {
    console.warn(`WARNING: ${reason}`);
  }
});

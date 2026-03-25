/**
 * Kai Data App - Express backend
 *
 * Handles:
 * - Service discovery (finds kai-assistant URL from Keboola Storage API)
 * - Proxies chat requests with proper auth headers
 * - Serves the static frontend
 *
 * Credentials come from environment variables (Keboola injects these in production)
 * or from .env.local for local development.
 */

require("dotenv").config({ path: ".env.local" });

const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static("public"));

const STORAGE_API_TOKEN = process.env.STORAGE_API_TOKEN || process.env.KBC_TOKEN || "";
const STORAGE_API_URL = process.env.STORAGE_API_URL || process.env.KBC_URL || "";

let _kaiBaseUrl = null;

/**
 * Discover the kai-assistant service URL from Keboola Storage API.
 */
async function discoverKaiUrl() {
  if (_kaiBaseUrl) return _kaiBaseUrl;

  const res = await fetch(`${STORAGE_API_URL.replace(/\/$/, "")}/v2/storage`, {
    headers: { "x-storageapi-token": STORAGE_API_TOKEN },
  });

  if (!res.ok) {
    throw new Error(`Storage API discovery failed: ${res.status} ${res.statusText}`);
  }

  const data = await res.json();
  const kaiService = (data.services || []).find((s) => s.id === "kai-assistant");

  if (!kaiService || !kaiService.url) {
    const available = (data.services || []).map((s) => s.id);
    throw new Error(`kai-assistant service not found. Available: ${available.join(", ")}`);
  }

  _kaiBaseUrl = kaiService.url.replace(/\/$/, "");
  console.log(`Discovered kai-assistant at: ${_kaiBaseUrl}`);
  return _kaiBaseUrl;
}

/**
 * Forward a POST request to kai-assistant and stream the SSE response back.
 * Shared by /api/chat and /api/chat/:chatId/:action/:approvalId routes.
 */
async function proxySSE(payload, res) {
  const kaiUrl = await discoverKaiUrl();

  const upstream = await fetch(`${kaiUrl}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-storageapi-token": STORAGE_API_TOKEN,
      "x-storageapi-url": STORAGE_API_URL,
    },
    body: JSON.stringify(payload),
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
 * GET /api/config
 * Returns non-secret config the frontend needs (just whether credentials exist).
 */
app.get("/api/config", (_req, res) => {
  res.json({
    hasCredentials: !!(STORAGE_API_TOKEN && STORAGE_API_URL),
  });
});

/**
 * POST /api/chat
 * Proxies chat messages to the kai-assistant backend.
 * Streams the SSE response back to the frontend.
 */
app.post("/api/chat", async (req, res) => {
  try {
    await proxySSE(req.body, res);
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
 * POST /api/chat/:chatId/:action/:approvalId
 * Approves or rejects a tool call and streams the continuation.
 * :action must be "approve" or "reject".
 */
app.post("/api/chat/:chatId/:action/:approvalId", async (req, res) => {
  try {
    const { chatId, action, approvalId } = req.params;
    const approved = action === "approve";

    const payload = {
      id: chatId,
      message: {
        id: crypto.randomUUID(),
        role: "user",
        parts: [
          {
            type: "tool-approval-response",
            approvalId,
            approved,
            ...(approved ? {} : { reason: "User denied" }),
          },
        ],
      },
      selectedChatModel: "chat-model",
      selectedVisibilityType: "private",
    };

    await proxySSE(payload, res);
  } catch (err) {
    console.error(`${req.params.action} error:`, err);
    if (!res.headersSent) {
      res.status(500).json({ error: err.message });
    } else {
      res.end();
    }
  }
});

app.listen(PORT, () => {
  console.log(`Kai Data App running at http://localhost:${PORT}`);
  if (!STORAGE_API_TOKEN || !STORAGE_API_URL) {
    console.warn("WARNING: Missing credentials. Create .env.local with STORAGE_API_TOKEN and STORAGE_API_URL");
  }
});

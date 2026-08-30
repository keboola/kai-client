# Kai Data App — JavaScript example

Minimal Express + vanilla-JS frontend that talks to the Keboola AI Assistant.

## Run locally

```bash
cp .env.example .env.local      # fill in STORAGE_API_TOKEN and STORAGE_API_URL
npm install
node server.js                  # serves http://localhost:3000
```

## Env vars

The required names are exact:

- `STORAGE_API_TOKEN` — Keboola Storage API token (the platform UI uses the same)
- `STORAGE_API_URL` — Storage API URL for your stack (see `.env.example`)

`KAI_TOKEN` and similar names are **not** recognised. The legacy `KBC_TOKEN` /
`KBC_URL` names are honoured as fallbacks only.

## Troubleshooting

### "Works in the Keboola platform UI but my app errors out"

Run `kai verify` from the same shell where you set the env vars:

```bash
pip install kai-client    # or: uv tool install kai-client
kai verify
```

It reports which project your token resolves to, whether the kai-assistant
service is reachable, and your current monthly message usage
(e.g. `19/150 messages used, 131 left`).

### Common errors

- **`429 rate_limit:chat — You have exceeded your maximum number of messages
  for this month.`** Your project hit its monthly chat-message limit. Note
  that the platform UI's "X / 150" counter is **per-token, server-side** —
  if the UI says you have messages left but the API says you don't, your
  app token and UI session may be hitting different counters. Contact
  Keboola support or wait for the reset date shown by `kai verify`.

- **`401 storage.tokenInvalid`** The token doesn't exist or has been
  expired/revoked. Generate a fresh one.

- **`kai-assistant service not found`** Your stack doesn't have the AI
  Assistant feature enabled, or `STORAGE_API_URL` points at the wrong stack.

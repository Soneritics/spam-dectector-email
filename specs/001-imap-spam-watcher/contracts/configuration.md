# Contract: Container Configuration (environment variables)

All configuration is supplied via environment variables (FR-013). Secrets are never baked into the image or logged (FR-014). The service validates configuration at startup and exits with a clear error if a required value is missing or invalid.

## Variables

| Env var | Required | Type | Notes |
|---------|----------|------|-------|
| `IMAP_HOST` | yes | hostname | Incoming mail server |
| `IMAP_PORT` | yes | int | e.g., 993 (implicit TLS) |
| `IMAP_USERNAME` | yes | string | Mailbox login |
| `IMAP_PASSWORD` | yes | secret | Mailbox password |
| `SMTP_HOST` | yes | hostname | Outgoing mail server |
| `SMTP_PORT` | yes | int | e.g., 465 (implicit TLS) or 587 (STARTTLS) |
| `SMTP_USERNAME` | yes | string | Outgoing login |
| `SMTP_PASSWORD` | yes | secret | Outgoing password |
| `WHITELIST_REGEX` | yes | regex | Matched against the `From` address; must compile |
| `CC_ADDRESSES` | no | string | `;`-separated list; empty/whitespace entries ignored |
| `DETECTOR_URL` | yes | URL | Absolute URL of the spam-check endpoint |
| `DETECTOR_FUNCTIONS_KEY` | yes | secret | Sent as `x-functions-key` |
| `DETECTOR_OPENAI_KEY` | yes | secret | Sent as `x-openai-api-key` |
| `DETECTOR_MODEL` | no | string | Sent as `x-openai-model` when set |
| `POLL_INTERVAL_SECONDS` | no | int | Default ~30–60; must be > 0 |
| `RETRY_MAX_ATTEMPTS` | no | int | Default 3; ≥ 1 |
| `RETRY_WINDOW_SECONDS` | no | int | Default ~90; bounds total retry time to ~1–2 min |

## Validation rules

- Missing any **required** variable ⇒ startup fails with a message naming the variable (no secret values echoed).
- `IMAP_PORT` / `SMTP_PORT` in 1–65535.
- `WHITELIST_REGEX` must compile; invalid regex ⇒ startup fails.
- `DETECTOR_URL` must be an absolute `http(s)` URL.
- `CC_ADDRESSES`: split on `;`, trim, drop empties; each remaining token must be a syntactically valid email.

## Deployment contract

- The container runs as a long-lived foreground process and MUST be deployed with `restart: unless-stopped` (FR-012).
- No mounted volume or database is required (stateless; expunge-after-send).

## Example (`.env.example`)

```dotenv
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USERNAME=spamwatch@example.com
IMAP_PASSWORD=change-me
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=spamwatch@example.com
SMTP_PASSWORD=change-me
WHITELIST_REGEX=^.*@example\.com$
CC_ADDRESSES=security@example.com;soc@example.com
DETECTOR_URL=https://spam-detector.azurewebsites.net/spam-check/email
DETECTOR_FUNCTIONS_KEY=change-me
DETECTOR_OPENAI_KEY=change-me
DETECTOR_MODEL=
POLL_INTERVAL_SECONDS=45
RETRY_MAX_ATTEMPTS=3
RETRY_WINDOW_SECONDS=90
```

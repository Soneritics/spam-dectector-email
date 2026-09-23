# Phase 0 Research: IMAP Spam Watcher

This document resolves the open technical choices for the IMAP Spam Watcher. The feature spec is technology-agnostic and the repository has no existing application code, so a stack is selected here. Each decision follows the Decision / Rationale / Alternatives format.

## 1. Implementation language & runtime

- **Decision**: Python 3.12.
- **Rationale**: The task is I/O-bound mail processing (IMAP read, MIME parsing, SMTP send, one HTTP call). Python's standard library covers MIME parsing/building and SMTP natively, mature IMAP libraries exist, and the resulting container is small and simple to operate. This maximizes clarity for a small maintenance-light worker.
- **Alternatives considered**: Node.js (`imapflow`/`nodemailer`) — equally capable but MIME/`.eml` handling is less batteries-included; Go — great for static binaries and footprint but more boilerplate for MIME/email construction. Either is viable; Python chosen for the richest standard-library email support and lowest code volume. *If the maintainer prefers another language, only this decision changes; the module boundaries in plan.md remain the same.*

## 2. IMAP access (fetch, extract, delete)

- **Decision**: `imap-tools`.
- **Rationale**: Provides a high-level API over `imaplib` for fetching messages, iterating attachments, reading the `From`/`Reply-To` headers, and flagging/expunging messages — matching the expunge-after-send lifecycle (Q1). It exposes the underlying `email.message.Message` for `.eml` extraction.
- **Alternatives considered**: raw `imaplib` (too low-level, error-prone parsing); `IMAPClient` (solid, but attachment/body extraction still requires manual `email` parsing). `imap-tools` gives the best ergonomics-to-dependency ratio.

## 3. Content extraction (attached original vs. body)

- **Decision**: Use the standard library `email` package. For each whitelisted message, look for an attached message part (`message/rfc822`, or an attachment whose filename ends in `.eml` / content type `message/rfc822`). If present, extract that original message's text and classify it; otherwise classify the received message's text body (prefer `text/plain`, fall back to stripped `text/html`). When multiple attached original messages exist, use the first in MIME order; when neither an attached original nor any textual body exists, treat the content as empty (a deterministic error).
- **Rationale**: Directly implements FR-004 and Clarification Q1 (2026-09-23 session 1). `message/rfc822` is the standard container clients use when forwarding "as attachment," which is common in report-as-spam workflows.
- **Alternatives considered**: Classifying the raw MIME source verbatim (would include forwarding boilerplate and MIME noise, degrading detector accuracy); HTML-only heuristics to strip quoting (rejected in clarify Q1 in favor of the attachment-first rule).

## 4. Outbound email construction & sending

- **Decision**: Build a `multipart/alternative` message with both a `text/plain` and a `text/html` part using `email.message.EmailMessage`; send via `smtplib.SMTP`/`SMTP_SSL` using the configured outgoing server, with STARTTLS when the port implies it. The subject is `Spam check: <original subject>` and content is written in English for v1 (FR-019); the spam/not-spam verdict is stated in text (not by color alone) with confidence rendered as a percentage (FR-008).
- **Rationale**: Implements FR-008 / Clarification Q1 (session 2): HTML reply with visually emphasized (color-coded) verdict plus a plain-text fallback for non-HTML clients. `EmailMessage` handles headers, CC, and multipart cleanly with no third-party dependency.
- **Alternatives considered**: `Jinja2` HTML templating (nice, but a single small template can be a Python f-string/`string.Template`, avoiding a dependency); third-party mailers (`emails`, `yagmail`) — unnecessary given standard-library coverage.

## 5. Spam Detector HTTP client & retry policy

- **Decision**: `httpx` with an explicit connect/read timeout; POST the extracted content as `text/plain`; send headers `x-functions-key`, `x-openai-api-key`, and optional `x-openai-model`. Apply a bounded retry with exponential backoff (with jitter): up to a configurable maximum (default 3 attempts) within a configurable window (default 90 s) for transient failures (connection errors, timeouts, HTTP 5xx / 502, and unexpected/undocumented status codes). Do **not** retry deterministic responses (400 empty body, 413 too large) — surface those as immediate error notifications.
- **Rationale**: Implements FR-005/FR-006/FR-010/FR-016 and Clarification Q2 (session 1). The 5xx/timeout-vs-4xx split matches the detector's documented status codes (`spam-detector-swagger.json`): 502 = upstream provider failure (retryable), 400/413 = client/content errors (not retryable).
- **Alternatives considered**: `requests` + `urllib3 Retry` (works, but ties retry to the adapter and is less explicit about the transient/deterministic split); `tenacity` for retry orchestration (a small hand-rolled loop keeps behavior obvious and testable). A simple explicit loop with capped attempts and sleep/backoff is preferred.

## 6. Response interpretation

- **Decision**: Parse the JSON `apiResult_spamResult` envelope. Treat `isError == true` (or a non-2xx status) as a failure path. On success, read `result.spam`, `result.confidence`, `result.reason`, and `result.promptInjectionDetected` for the reply. Include `errorMessage` (when present) in error notifications.
- **Rationale**: Matches the documented schema and FR-008 reply fields. Keeps the reply informative and the error notification actionable.
- **Alternatives considered**: Trusting only the HTTP status (insufficient — the envelope carries `isError`/`errorMessage` even on 200-style wrappers).

## 7. Configuration management

- **Decision**: `pydantic-settings` `BaseSettings` model reading all values from environment variables, with validation (required vs. optional, port ranges, non-empty secrets, CC list parsing). A `.env.example` documents every variable.
- **Rationale**: Implements FR-013/FR-014 — a single typed config surface, validated at startup (fail fast on missing/invalid config), and secrets sourced from the environment rather than code. Semicolon-separated CC parsing and whitelist regex compilation happen here so failures are caught early.
- **Alternatives considered**: Manual `os.environ` reads (no validation, scattered); a config file baked into the image (risks committing secrets — rejected by FR-014).

## 8. Structured logging (no secrets / no content)

- **Decision**: Standard `logging` configured with `python-json-logger` to emit one structured JSON record per lifecycle event (startup, IMAP/SMTP/detector connectivity, and per-message: received → whitelisted/ignored → verdict|error → send result, with timing). A small redaction discipline ensures secrets and full message bodies are never included; log only sender address, subject, message id, verdict, confidence, and error category.
- **Rationale**: Implements FR-017 and SC-008 while honoring FR-014. JSON logs are greppable and container-friendly.
- **Alternatives considered**: `structlog` (excellent but heavier for this size); plain text logging (harder to trace outcomes programmatically per SC-008).

## 9. Idempotency & restart recovery (no persistence)

- **Decision**: Process messages currently present in the mailbox; permanently delete (expunge) a message — not merely move it to Trash — only after its reply/error has been successfully sent. Keep no local processed-state store.
- **Rationale**: Implements FR-011 and Clarification Q1 (session 1). Because deletion follows a successful send, a crash before sending leaves the message for retry on restart; a crash in the narrow window after send but before delete may cause a single duplicate reply — the accepted trade-off for avoiding a persistent store (documented in spec Edge Cases).
- **Alternatives considered**: Persisting processed message-ids to a mounted volume/SQLite (adds storage + volume ops for a marginal reduction in an already-rare duplicate window — rejected for v1); relying on the IMAP `\Seen` flag without deletion (leaves the mailbox growing and complicates "pending" detection).

## 10. Self-reply loop avoidance

- **Decision**: Send outbound replies/notifications from an address (or via an outgoing server) distinct from the monitored mailbox, and additionally guard by ignoring any inbound message whose `From` does not match the whitelist (the reply's From will not be whitelisted). Optionally skip messages the service recognizes as its own by a custom header (e.g., `X-Spam-Watcher: reply`).
- **Rationale**: Implements FR-015. The whitelist already blocks non-whitelisted senders; the custom-header guard defends the case where the monitored mailbox also receives copies of its own outbound mail.
- **Alternatives considered**: No guard (risky if the outbound and monitored mailboxes overlap); subject-prefix detection (fragile). A dedicated header is deterministic and cheap.

## 11. Transport security (TLS)

- **Decision**: Use TLS for IMAP (implicit TLS 993), SMTP (implicit TLS 465 or STARTTLS 587), and the detector (HTTPS) whenever the server/endpoint supports it, selected by configured port. When a mail server does not support TLS, permit an unencrypted fallback (accepted residual risk per Clarifications 2026-09-23, Q4 — operators are strongly advised to use TLS-capable servers).
- **Rationale**: Matches the spec's Transport-security decision; TLS protects credentials and content in transit, while the documented fallback keeps the watcher usable against legacy/internal servers at the operator's explicit risk.
- **Alternatives considered**: Hard-fail on any non-TLS connection (rejected in favor of the spec's configurable fallback); plaintext by default (unnecessarily insecure).

## 12. Containerization & always-on operation

- **Decision**: A slim `python:3.12-slim` image running the worker as a foreground process (PID 1 via a minimal entrypoint), deployed with `restart: unless-stopped` in `docker-compose.yml`; configuration injected as environment variables.
- **Rationale**: Implements FR-012. Foreground process + Docker restart policy provides automatic recovery without an in-app supervisor. The poll loop resumes cleanly since state lives in the mailbox.
- **Alternatives considered**: A process supervisor (supervisord) inside the container (unnecessary for a single process); a cron-style one-shot container (loses the "always watching / near-real-time" behavior and the 2-minute target).

## 13. Testing strategy

- **Decision**: `pytest` with three layers — unit (whitelist matching, `.eml` vs body extraction, retry/backoff decision table, email rendering, config validation, CC parsing) with mocked boundaries; integration against a disposable **GreenMail** container providing IMAP + SMTP to exercise fetch → classify (stub detector) → send → expunge; a contract test asserting request shape (headers, `text/plain` body) and response handling against the documented `apiResult_spamResult` schema via a stub HTTP server.
- **Rationale**: Covers the acceptance scenarios and success criteria (SC-001..SC-009) at proportionate cost; GreenMail gives real IMAP/SMTP semantics without external accounts.
- **Alternatives considered**: MailHog (SMTP only — cannot exercise the IMAP fetch/expunge path); live test mailbox (flaky, credential-bound — reserved for manual quickstart validation).

## Resolved unknowns

All Technical Context items are resolved; no `NEEDS CLARIFICATION` markers remain. The two spec-level clarifications (content extraction, detector OpenAI key) and the four operational clarifications (idempotency, retry bounds, logging, rate limiting) plus the two UX clarifications (reply format, authoritative sender) were settled during `/speckit-clarify` and are reflected above.

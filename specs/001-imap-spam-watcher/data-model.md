# Data Model: IMAP Spam Watcher

The service is stateless (no database). The "entities" below are in-memory value objects that flow through one processing pass, plus the startup configuration. Types are expressed language-neutrally; the reference implementation uses Python dataclasses / pydantic models.

## Entity: Configuration

Loaded once at startup from environment variables; validated (fail-fast) before the poll loop starts. See [contracts/configuration.md](./contracts/configuration.md) for the exact variable names and formats.

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `imap_host` | string | yes | non-empty hostname |
| `imap_port` | int | yes | 1–65535 (typically 993) |
| `imap_username` | string | yes | non-empty |
| `imap_password` | secret string | yes | non-empty; never logged |
| `smtp_host` | string | yes | non-empty hostname |
| `smtp_port` | int | yes | 1–65535 (typically 465/587) |
| `smtp_username` | string | yes | non-empty |
| `smtp_password` | secret string | yes | non-empty; never logged |
| `whitelist_regex` | string (regex) | yes | must compile as a valid regular expression |
| `cc_addresses` | list<string> | no | parsed from a `;`-separated string; empty entries/whitespace ignored; each a valid email |
| `detector_url` | string (URL) | yes | absolute http(s) URL of the spam-check endpoint |
| `detector_functions_key` | secret string | yes | non-empty; sent as `x-functions-key`; never logged |
| `detector_openai_key` | secret string | yes | non-empty; sent as `x-openai-api-key`; never logged |
| `detector_model` | string | no | optional; sent as `x-openai-model` when set |
| `poll_interval_seconds` | int | no | default 45; > 0 |
| `retry_max_attempts` | int | no | default 3; ≥ 1 |
| `retry_window_seconds` | int | no | default ~90 (bounds total retry time to ~1–2 min) |

**Relationships**: singleton for the process lifetime; injected into `mailbox`, `detector`, and `notifier`.

## Entity: IncomingRequest

Derived from a message fetched from the monitored mailbox.

| Field | Type | Notes |
|-------|------|-------|
| `message_uid` | string | IMAP identifier used to delete the message after send |
| `from_address` | string | parsed from the `From` header — used for whitelist matching (FR-002) |
| `reply_to_address` | string \| null | parsed from `Reply-To`; when present it is the reply target (FR-007) |
| `subject` | string | original subject; referenced in the reply subject |
| `content_to_classify` | string | the attached original message's text when a `message/rfc822`/`.eml` attachment exists, else the received body (FR-004) |
| `content_source` | enum(`attached_original`, `message_body`) | which source was used; surfaced in the reply |
| `received_at` | timestamp | for timing/observability |

**Validation / rules**:
- If `from_address` does not match `whitelist_regex` → the message is **ignored**: no classification, no reply, and (per expunge-after-send) it is left in place or handled per operator policy; nothing is sent (FR-003).
- If `content_to_classify` is empty → treated as a deterministic error (no detector retry); an error notification is sent (FR-010, Edge Cases).

**Lifecycle (state transitions)**:

```
fetched
  └─ whitelisted? ── no ──▶ ignored (terminal; no send)
        │ yes
        ▼
   content extracted
        │
        ▼
   classified ──(transient failure)──▶ retry (≤ N attempts / window)
        │  success                              │ exhausted
        ▼                                        ▼
   verdict reply built                     error notification built
        └───────────────┬────────────────────────┘
                        ▼
                 response sent (SMTP)
                        │ success
                        ▼
                 message expunged (terminal)
```

A message is permanently expunged **only** after `response sent` succeeds (FR-011). A failure before sending leaves the message for a later poll.

## Entity: ClassificationResult

Parsed from the detector's `apiResult_spamResult` response (see [contracts/spam-detector-api.md](./contracts/spam-detector-api.md)).

| Field | Type | Notes |
|-------|------|-------|
| `spam` | bool | primary verdict |
| `confidence` | float | 0.0–1.0 (double per schema) |
| `prompt_injection_detected` | bool | surfaced prominently in the reply (FR-008) |
| `reason` | string | detector's explanation |
| `is_error` | bool | envelope `isError` |
| `http_code` | int | envelope `httpCode` |
| `error_message` | string \| null | envelope `errorMessage`; used for error notifications |

**Rules**: `is_error == true` or a non-success HTTP status routes to the error-notification path rather than the verdict-reply path.

## Entity: Notification (Reply or Error)

The outbound email built from a `ClassificationResult` (verdict) or a failure (error). See [contracts/email-interface.md](./contracts/email-interface.md).

| Field | Type | Notes |
|-------|------|-------|
| `to_address` | string | `reply_to_address` when present, else `from_address` (FR-007) |
| `cc_addresses` | list<string> | configured CC list; empty when unset (FR-009) |
| `subject` | string | references the original subject (e.g., `Spam check: <original subject>`) |
| `kind` | enum(`verdict`, `error`) | selects body template |
| `html_body` | string | HTML with color-coded verdict (verdict kind) (FR-008) |
| `text_body` | string | plain-text fallback / error description (FR-008, FR-010) |
| `headers` | map | includes an identifying header (e.g., `X-Spam-Watcher: reply`) to avoid self-reprocessing (FR-015) |

**Rules**:
- Verdict notifications include: spam/not-spam (emphasized), confidence, reason, prompt-injection status, and `content_source`.
- Error notifications include a human-readable failure description (derived from `error_message`/exception category) and never leak secrets.

## Entity: SenderWhitelistRule

| Field | Type | Notes |
|-------|------|-------|
| `pattern` | compiled regex | from `whitelist_regex`; compiled once at startup |

**Rules**: a single pattern matched against `IncomingRequest.from_address`; non-match ⇒ ignore (FR-003).

## Notes

- No entity is persisted; "processed state" is represented by the message's **absence** from the mailbox after a successful send.
- All secret-typed fields must be excluded from logs and error notifications (FR-014).

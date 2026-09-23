# Implementation Plan: IMAP Spam Watcher

**Branch**: `001-imap-spam-watcher` | **Date**: 2026-09-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-imap-spam-watcher/spec.md`

## Summary

A long-running, containerized background service watches a single IMAP mailbox. When a whitelisted user (matched on the `From` header) forwards a suspicious email, the service extracts the content to classify (an attached original `.eml` when present, otherwise the received body), submits it as `text/plain` to the external Spam Detector Azure Function (`x-functions-key` + `x-openai-api-key` headers, optional model override), and replies to the requester (Reply-To when present, else From) with an HTML + plain-text result email (subject `Spam check: <subject>`, English v1) conveying the spam verdict, confidence (as a percentage), reason, prompt-injection status, and which content was evaluated. Transient detector failures are retried with exponential backoff up to a configurable maximum (default 3 attempts within a 90 s window) — unexpected status codes are treated as transient — before a content-safe error notification is sent; deterministic errors notify immediately. Only a successful status with `isError=false` yields a verdict (FR-020). Each message is permanently expunged from the mailbox (not moved to Trash) only after its response is sent (no local persistence; content is handled in memory only, FR-018), giving effectively exactly-once behavior with restart recovery. Configuration is validated at startup and fails fast (FR-021). The service runs with `restart: unless-stopped` and emits structured per-message logs that never contain secrets or full message content.

**Technical approach**: A small Python worker built around a poll loop. Discrete modules handle configuration (env vars, validated at startup), IMAP fetch/extract/expunge, the detector HTTP call with bounded retry, and multipart HTML/plain-text SMTP notification. State is intentionally externalized to the mailbox (expunge-after-send) so no database or volume is required.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `imap-tools` (IMAP fetch, attachment access, flag/delete), Python standard library `email` (MIME parsing, `.eml` extraction, multipart build) + `smtplib` (send), `httpx` (detector HTTP client with explicit timeouts), `pydantic-settings` (typed configuration from environment variables), `python-json-logger` (structured JSON logging)

**Storage**: N/A — stateless. Processed messages are permanently expunged from the mailbox after their response is sent; email content is handled in memory only; no local persistence, database, or mounted volume is required (per Clarifications 2026-09-23, Q1).

**Testing**: `pytest`. Unit tests with mocked IMAP/SMTP/HTTP boundaries; integration tests against a disposable GreenMail container exposing IMAP + SMTP; a consumer contract test that validates request shaping and response handling against the Spam Detector schema using a stub server.

**Target Platform**: Linux Docker container (amd64), orchestrated via Docker Compose with `restart: unless-stopped`.

**Project Type**: Single project — a background worker/daemon (no user-facing HTTP surface; triggered by email).

**Performance Goals**: Deliver a verdict or error to the requester within 2 minutes of message arrival under normal conditions (SC-001). Poll interval ~30–60 s. Human-driven, modest volume.

**Constraints**: Always-on with automatic restart (FR-012); never log secrets or full message content (FR-014, FR-017); in-memory-only content handling with permanent expunge (FR-018); bounded detector retry (configurable; default 3 attempts within a 90 s window, exponential backoff, FR-010/FR-016); startup config validation / fail-fast (FR-021); no self-reply loops (FR-015); small memory/CPU footprint.

**Scale/Scope**: One monitored mailbox and one detector endpoint per running container; a small set of trusted whitelisted senders; no rate limiting in v1 (out of scope per Clarifications Q4).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) currently contains only unfilled template placeholders — no principles have been ratified. There are therefore no project-specific gates to enforce. In their absence, the following general good-practice gates are applied:

| Gate | Status | Notes |
|------|--------|-------|
| Simplicity (avoid unnecessary components) | PASS | Single project; no database/queue/broker — state externalized to the mailbox. |
| Testability | PASS | I/O boundaries (IMAP, SMTP, HTTP) isolated behind thin modules to enable mocking + integration tests. |
| Security of secrets | PASS | All credentials via env/secret config; never logged or persisted (FR-014). |
| Observability | PASS | Structured per-message outcome logging defined (FR-017, SC-008). |
| No speculative scope | PASS | Rate limiting, multi-mailbox, UI explicitly deferred (spec Out of scope). |

**Result**: PASS (no violations; Complexity Tracking not required). Re-evaluated post-design in Phase 1 — still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-imap-spam-watcher/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── spam-detector-api.md      # Consumed HTTP contract (Azure Function)
│   ├── email-interface.md        # Inbound request + outbound reply/error email contract
│   └── configuration.md          # Container configuration (environment variable) contract
├── checklists/
│   ├── requirements.md  # Spec quality checklist (from /speckit-specify)
│   └── quality-gate.md  # Requirements-quality gate checklist (from /speckit-checklist)
└── tasks.md             # Phase 2 output (/speckit-tasks - NOT created here)
```

### Source Code (repository root)

```text
src/
└── spam_watcher/
    ├── __init__.py
    ├── app.py            # Entry point: build config, wire dependencies, run poll loop
    ├── config.py         # pydantic-settings model mapping env vars -> typed Settings
    ├── logging_setup.py  # Structured (JSON) logging configuration; secret/content redaction
    ├── models.py         # Dataclasses: IncomingRequest, ClassificationResult, Notification
    ├── mailbox.py        # IMAP: fetch pending messages, extract content, expunge after send
    ├── detector.py       # HTTP client to the Spam Detector (headers, timeout, bounded retry)
    ├── notifier.py       # SMTP: build multipart HTML+text reply/error, address & send
    └── processor.py      # Orchestration: whitelist -> extract -> classify -> notify -> delete

tests/
├── unit/                 # Whitelist, content extraction, retry policy, email rendering, config
├── integration/          # End-to-end against GreenMail (IMAP+SMTP) + stub detector
└── contract/             # Detector request/response conformance to the documented schema

Dockerfile               # Slim Python base image; runs spam_watcher
docker-compose.yml       # Service definition with restart: unless-stopped + env
.env.example             # Documented, non-secret template of required configuration
pyproject.toml           # Project metadata + dependencies + tooling (pytest, ruff)
README.md                # Operator-facing overview and links to quickstart
```

**Structure Decision**: Single Python project. The worker is small and cohesive, so a flat `spam_watcher` package with one module per responsibility (config, mailbox, detector, notifier, processor, app) keeps I/O boundaries isolated for testing while avoiding layered/microservice complexity that the modest scope does not justify.

## Complexity Tracking

No constitution violations — this section is intentionally empty.

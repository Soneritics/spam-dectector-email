---

description: "Task list for IMAP Spam Watcher implementation"
---

# Tasks: IMAP Spam Watcher

**Input**: Design documents from `/specs/001-imap-spam-watcher/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the plan (Testing) and quickstart define a unit/integration/contract test strategy, and the contracts specify test expectations.

**Organization**: Tasks are grouped by user story (US1–US4 from spec.md) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story the task belongs to
- Stack: Python 3.12; package `src/spam_watcher/`; tests under `tests/{unit,integration,contract}/`

## Path Conventions

Single project. Application code in `src/spam_watcher/`, tests in `tests/`, container/config files at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and container scaffolding

- [x] T001 Create project structure: `src/spam_watcher/` package (with `__init__.py`) and `tests/unit/`, `tests/integration/`, `tests/contract/` directories per plan.md
- [x] T002 Initialize Python 3.12 project in `pyproject.toml` with runtime deps (`imap-tools`, `httpx`, `pydantic-settings`, `python-json-logger`) and dev deps (`pytest`, `ruff`), including ruff + pytest configuration
- [x] T003 [P] Create `.env.example` at repo root enumerating every variable from contracts/configuration.md (IMAP_*, SMTP_*, WHITELIST_REGEX, CC_ADDRESSES, DETECTOR_URL, DETECTOR_FUNCTIONS_KEY, DETECTOR_OPENAI_KEY, DETECTOR_MODEL, POLL_INTERVAL_SECONDS, RETRY_MAX_ATTEMPTS, RETRY_WINDOW_SECONDS)
- [x] T004 [P] Create `Dockerfile` (`python:3.12-slim`, foreground entrypoint running `spam_watcher`) and `docker-compose.yml` with `restart: unless-stopped` and env wiring per contracts/configuration.md (FR-012)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure required by every user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 [P] Implement typed `Settings` config in `src/spam_watcher/config.py` using pydantic-settings for all env vars, with startup validation and fail-fast: required-vs-optional per contracts/configuration.md, `IMAP_PORT`/`SMTP_PORT` in `1–65535`, `WHITELIST_REGEX` must compile, `DETECTOR_URL` absolute http(s), CC split on `;` + trim + drop empties (each a valid email), defaults `POLL_INTERVAL_SECONDS`~45, `RETRY_MAX_ATTEMPTS`=3, `RETRY_WINDOW_SECONDS`=90; on invalid config log a clear error naming the setting without echoing secret values (FR-013, FR-021, FR-009)
- [x] T006 [P] Implement structured JSON logging in `src/spam_watcher/logging_setup.py` with a redaction discipline that never logs secrets or full message content (FR-014, FR-017)
- [x] T007 [P] Define domain models in `src/spam_watcher/models.py` per data-model.md: `IncomingRequest` (message_uid, from_address, reply_to_address, subject, content_to_classify, content_source enum `attached_original`|`message_body`, received_at), `ClassificationResult` (spam bool, confidence float 0.0–1.0, prompt_injection_detected bool, reason str, is_error bool, http_code int, error_message str|null), `Notification` (to_address, cc_addresses, subject, kind enum `verdict`|`error`, html_body, text_body, headers), `SenderWhitelistRule` (compiled pattern)
- [x] T008 [P] Implement IMAP client in `src/spam_watcher/mailbox.py`: connect over TLS when supported with plaintext fallback, fetch every message currently present as pending, and permanently expunge a message (not move to Trash) only via an explicit post-send call (FR-001, FR-011, FR-018; depends on T005, T007)
- [x] T009 [P] Implement SMTP client in `src/spam_watcher/notifier.py`: connect (implicit TLS/STARTTLS by port, plaintext fallback), build a `multipart/alternative` message (HTML + plain text), address to Reply-To else From, and set an `X-Spam-Watcher: reply` identifying header (FR-007, FR-015, FR-019; depends on T005, T007)
- [x] T010 [P] Implement detector HTTP client in `src/spam_watcher/detector.py`: POST content as `text/plain` with headers `x-functions-key`, `x-openai-api-key`, and optional `x-openai-model`, with explicit connect/read timeouts, and parse the `apiResult_spamResult` envelope per contracts/spam-detector-api.md (FR-005, FR-006; depends on T005, T007)
- [x] T011 Implement processor skeleton and poll loop in `src/spam_watcher/processor.py` and `src/spam_watcher/app.py`: load config, wire mailbox/detector/notifier, iterate pending messages applying the sender whitelist gate first — evaluate the From-header address against the compiled pattern and ignore (no classification, no reply) any non-match (FR-002, FR-003) — and run a continuous restart-safe loop honoring `POLL_INTERVAL_SECONDS` (FR-001, FR-012; depends on T005–T010)

**Checkpoint**: Foundation ready — user story implementation can begin

---

## Phase 3: User Story 1 - Get a spam verdict for a forwarded email (Priority: P1) 🎯 MVP

**Goal**: A forwarded message is classified and a clear HTML+text verdict is sent back to the requester.

**Independent Test**: Forward an email (ideally as a `.eml` attachment) from a configured sender; confirm an HTML reply (with plain-text fallback) arrives stating spam/not-spam, confidence %, reason, prompt-injection status, and which content was evaluated, and the source message is expunged.

### Tests for User Story 1

- [x] T012 [P] [US1] Contract test in `tests/contract/test_detector_contract.py`: asserts POST `text/plain` body, required headers (`x-functions-key`, `x-openai-api-key`; `x-openai-model` only when configured), and that a `200` + `isError=false` payload maps to all four `result` fields, per contracts/spam-detector-api.md
- [x] T013 [P] [US1] Integration test in `tests/integration/test_verdict_flow.py`: whitelisted forward with a `.eml` attachment via GreenMail + stub detector → HTML+text verdict reply delivered to sender; source message expunged
- [x] T014 [P] [US1] Unit test in `tests/unit/test_extraction.py`: attached `message/rfc822`/`.eml` is chosen (first in MIME order) over the body; body used when no attachment; empty when neither body nor attachment (FR-004)

### Implementation for User Story 1

- [x] T015 [P] [US1] Implement content extraction in `src/spam_watcher/processor.py`: classify the attached original message (first `message/rfc822`/`.eml` in MIME order) when present, else the textual body; produce empty content when neither exists; set `content_source` (FR-004)
- [x] T016 [US1] Implement classification call + response mapping in `src/spam_watcher/detector.py`: send extracted content, map `result.spam/confidence/reason/promptInjectionDetected`, and treat any non-2xx status or `isError=true` as a failure (FR-005, FR-006, FR-020; extends T010)
- [x] T017 [US1] Implement verdict reply build in `src/spam_watcher/notifier.py`: multipart HTML+text stating the spam/not-spam outcome in text (not color alone), confidence as a percentage (0–100%), reason, prompt-injection status, and content source; subject `Spam check: <original subject>`; English (FR-008, FR-019; extends T009)
- [x] T018 [US1] Wire the happy path in `src/spam_watcher/processor.py`: extract → classify → send verdict → expunge, producing exactly one reply and expunging only after a successful send (FR-011, FR-018, FR-001; depends on T015–T017)

**Checkpoint**: User Story 1 is fully functional and independently testable (MVP)

---

## Phase 4: User Story 2 - Only authorized senders are served (Priority: P2)

**Goal**: Messages whose `From` does not match the whitelist are ignored (no classification, no reply); the service cannot be used as a reflector.

**Independent Test**: Send from a non-matching address → no detector call and no reply; send from a matching address → normal processing.

### Tests for User Story 2

- [x] T019 [P] [US2] Unit test in `tests/unit/test_whitelist.py`: regex matched against the address portion of `From` only (excludes display name), case-insensitive, first address used when multiple; non-match → ignored (FR-002, FR-003)
- [x] T020 [P] [US2] Integration test in `tests/integration/test_whitelist_gate.py`: a non-whitelisted sender produces zero detector calls and zero outbound messages

### Implementation for User Story 2

- [x] T021 [US2] Finalize and verify the whitelist gate (core enforcement wired in Foundational T011) in `src/spam_watcher/processor.py`: confirm address-only, case-insensitive, first-address matching and the silent-ignore path (no classification, no reply) (FR-002, FR-003)
- [x] T022 [US2] Implement self-reply-loop guard in `src/spam_watcher/processor.py`: skip inbound messages bearing the `X-Spam-Watcher` header or whose `From` is non-whitelisted so the service never reprocesses its own outbound mail (FR-015)

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Receive a clear explanation when processing fails (Priority: P2)

**Goal**: When classification cannot complete, the requester still receives a content-safe error email instead of silence.

**Independent Test**: Point the watcher at a failing/unreachable detector → after bounded retries the sender receives an error email whose body describes the failure and contains no secrets/content; a `400/413` yields an immediate error email with no retry.

### Tests for User Story 3

- [x] T023 [P] [US3] Unit test in `tests/unit/test_retry_policy.py`: transient (timeout, connectivity, 5xx, unknown status) → retried; deterministic (400 empty, 413 oversized, empty content) → no retry (FR-010, FR-016, FR-020)
- [x] T024 [P] [US3] Integration test in `tests/integration/test_error_notification.py`: failing detector → bounded retries (default 3 / 90s) then exactly one error notification whose body excludes secrets, original content, and stack traces

### Implementation for User Story 3

- [x] T025 [US3] Implement bounded retry with backoff in `src/spam_watcher/detector.py`: up to `RETRY_MAX_ATTEMPTS` (default 3) within `RETRY_WINDOW_SECONDS` (default 90) for transient failures incl. unexpected status codes; deterministic failures fail immediately (FR-010, FR-016, FR-020; extends T016)
- [x] T026 [US3] Implement content-safe error notification in `src/spam_watcher/notifier.py` and `src/spam_watcher/processor.py`: body limited to a human-readable description, the detector's `errorMessage`, and a non-sensitive category; never secrets/credentials, original content, or raw stack traces; addressed to Reply-To else From (FR-010)
- [x] T027 [US3] Handle deterministic content errors (empty/oversized) without a detector call and retry outgoing-mail-server failures on later polls in `src/spam_watcher/processor.py` (FR-004, FR-016; Edge Cases)
- [x] T027a [US3] Handle malformed/unparseable MIME in `src/spam_watcher/processor.py`: skip the message without crashing the watcher, and send an error notification only when the sender is identifiable (Edge Cases)

**Checkpoint**: User Stories 1–3 independently functional

---

## Phase 6: User Story 4 - Keep configured recipients informed via CC (Priority: P3)

**Goal**: Configured CC addresses receive copies of every verdict reply and error notification.

**Independent Test**: With CC configured, both the sender and all CC addresses receive the message; with none configured, only the sender is addressed; malformed/empty CC entries are ignored.

### Tests for User Story 4

- [x] T028 [P] [US4] Unit test in `tests/unit/test_cc_parsing.py`: `"a@x.com; ;  b@y.com "` → `[a@x.com, b@y.com]`; empty config → no CC (FR-009)
- [x] T029 [P] [US4] Integration test in `tests/integration/test_cc.py`: CC applied to both verdict and error emails; when unset only the sender is addressed

### Implementation for User Story 4

- [x] T030 [US4] Apply the configured CC list to every outgoing verdict reply and error notification in `src/spam_watcher/notifier.py` (FR-009)

**Checkpoint**: All user stories independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, observability verification, and end-to-end validation

- [x] T031 [P] Config validation test in `tests/unit/test_config_validation.py`: missing/invalid settings (uncompilable regex, bad URL/port) cause a clear startup error naming the setting and no secret values are echoed (FR-021, FR-013)
- [x] T032 [P] Logging redaction test in `tests/unit/test_logging_redaction.py`: no secrets or full message content appear in logs, and each per-message record includes message id, sender, subject, decision, verdict/confidence when classified, error category when failed, and timing (FR-014, FR-017, SC-008)
- [x] T033 [P] Data-handling test in `tests/integration/test_data_handling.py`: no email content/attachments written to disk during processing and processed messages are permanently expunged (FR-018, SC-009)
- [x] T033a [P] Restart-recovery integration test in `tests/integration/test_restart_recovery.py`: a message left unprocessed at restart is processed exactly once afterward (SC-006, FR-011)
- [x] T034 [P] Write `README.md` operator guide linking to quickstart.md and documenting configuration
- [x] T035 Finalize Docker entrypoint (foreground PID 1) and verify `restart: unless-stopped` in `Dockerfile` and `docker-compose.yml` (FR-012, SC-006)
- [x] T036 Verify transport security handling (implicit TLS/STARTTLS by port, HTTPS detector, documented plaintext fallback) in `src/spam_watcher/mailbox.py` and `src/spam_watcher/notifier.py`
- [x] T037 Execute quickstart.md validation scenarios A–E and confirm SC-001…SC-009 outcomes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phase 3–6)**: All depend on Foundational; can then proceed in parallel or in priority order (US1 → US2 → US3 → US4)
- **Polish (Phase 7)**: Depends on the desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — no dependency on other stories (MVP)
- **US2 (P2)**: Core whitelist enforcement is wired in Foundational (T011); US2 verifies matching semantics and adds the self-reply guard; independently testable
- **US3 (P2)**: After Foundational — adds the failure path; independently testable
- **US4 (P3)**: After Foundational — adds CC to existing outbound paths; independently testable

### Within Each User Story

- Tests are written first and should fail before implementation
- Extraction/model work before service wiring; services before processor wiring

### Parallel Opportunities

- Setup: T003, T004 in parallel
- Foundational: T005–T010 in parallel (distinct files); T011 after them
- US1 tests T012–T014 in parallel; US2 tests T019–T020; US3 tests T023–T024; US4 tests T028–T029
- Polish: T031–T034 in parallel
- With capacity, US1–US4 can be built in parallel by different developers after Phase 2

---

## Parallel Example: User Story 1

```bash
# Tests for User Story 1 together:
Task: "Contract test in tests/contract/test_detector_contract.py"
Task: "Integration test in tests/integration/test_verdict_flow.py"
Task: "Unit test in tests/unit/test_extraction.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational)
2. Complete Phase 3 (US1)
3. **STOP and VALIDATE**: forward a whitelisted email and confirm the verdict reply
4. Deploy/demo the MVP (the whitelist gate is enforced from Foundational T011, so only authorized senders are processed)

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → verdict replies (MVP)
3. US2 → whitelist enforcement / anti-abuse
4. US3 → error notifications
5. US4 → CC recipients
6. Polish → hardening + quickstart validation

---

## Notes

- [P] = different files, no dependencies on incomplete tasks
- [Story] label maps each task to a user story for traceability
- Verify tests fail before implementing
- Commit after each task or logical group
- Secrets and full message content must never be logged or persisted (FR-014, FR-018)

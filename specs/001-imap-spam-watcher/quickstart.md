# Quickstart: IMAP Spam Watcher

A validation guide to configure, run, and prove the IMAP Spam Watcher works end-to-end. It references the [data model](./data-model.md) and [contracts](./contracts/) rather than repeating field details. Implementation code is out of scope here (see `tasks.md` after `/speckit-tasks`).

## Prerequisites

- Docker + Docker Compose installed.
- Access to an IMAP mailbox (incoming) and an SMTP account (outgoing). For local validation you can use a disposable **GreenMail** container that speaks both IMAP and SMTP.
- A reachable Spam Detector endpoint and its `x-functions-key` + `x-openai-api-key`. For local validation, a stub HTTP server that returns the `apiResult_spamResult` shape is sufficient.

## 1. Configure

Copy the template and fill in values (see [contracts/configuration.md](./contracts/configuration.md) for every variable and its validation):

```bash
cp .env.example .env
# edit .env: mail server hosts/ports/credentials, WHITELIST_REGEX, DETECTOR_URL, keys
```

Minimum required: `IMAP_*`, `SMTP_*`, `WHITELIST_REGEX`, `DETECTOR_URL`, `DETECTOR_FUNCTIONS_KEY`, `DETECTOR_OPENAI_KEY`.

## 2. Build & run

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

**Expected**: startup logs (JSON) showing config loaded, IMAP and SMTP connectivity OK, and the poll loop starting. No secret values appear in any log line (FR-014).

## 3. End-to-end validation scenarios

### Scenario A — Happy path verdict (validates SC-001, FR-004/005/007/008)

1. From a **whitelisted** address (matching `WHITELIST_REGEX`), forward a suspicious email to the monitored mailbox — ideally *as an attachment* (`.eml`) to exercise the attached-original path.
2. Wait up to the poll interval + classification time (target < 2 minutes).

**Expected**: A reply arrives at the sender (or its `Reply-To`) that is an HTML email (with plain-text fallback) stating spam / not spam (color-emphasized), confidence, reason, prompt-injection status, and which content was evaluated. Logs show `received → whitelisted → verdict → sent` with timing, and the source message is gone from the mailbox.

### Scenario B — Non-whitelisted sender is ignored (validates SC-002, FR-003)

1. Send an email from an address that does **not** match `WHITELIST_REGEX`.

**Expected**: No reply is sent and no detector call is made. Logs show the message was ignored. (No outbound email is generated.)

### Scenario C — CC recipients (validates SC-007, FR-009)

1. Set `CC_ADDRESSES=a@example.com;  ;b@example.com` and restart.
2. Trigger Scenario A again.

**Expected**: Both the sender and `a@example.com`, `b@example.com` receive the reply; the empty entry is ignored.

### Scenario D — Detector error notification (validates SC-004, FR-010)

1. Point `DETECTOR_URL` at an endpoint that returns `502` (transient) or `400` (deterministic), or stop the stub.
2. Trigger Scenario A.

**Expected**: For transient errors, the watcher retries (~3 attempts over ~1–2 min) then emails an error notification; for `400/413` it notifies immediately without retrying. The notification body describes the failure and contains no secrets. Exactly one outbound message is sent (SC-003).

### Scenario E — Restart recovery (validates SC-006, FR-011/012)

1. While a message is unprocessed in the mailbox, `docker compose restart`.

**Expected**: After restart the watcher resumes and processes the pending message exactly once (it was not deleted because no response had been sent yet).

## 4. Automated tests

```bash
# unit + contract (fast, mocked/stubbed boundaries)
pytest tests/unit tests/contract

# integration against GreenMail (IMAP+SMTP) + stub detector
pytest tests/integration
```

**Expected**: all suites green. See [contracts/spam-detector-api.md](./contracts/spam-detector-api.md) and [contracts/email-interface.md](./contracts/email-interface.md) for the assertions each layer must satisfy.

## 5. Teardown

```bash
docker compose down
```

## Success signals mapped

| Scenario | Success Criteria |
|----------|------------------|
| A | SC-001, SC-005 |
| B | SC-002 |
| C | SC-007 |
| D | SC-003, SC-004, SC-008 |
| E | SC-006 |

# IMAP Spam Watcher

A long-running, containerized service that watches an IMAP mailbox. When a **whitelisted** user
forwards a suspicious email to the monitored address, the watcher classifies it via the
[Spam Detector](https://github.com/Soneritics/spam-dectector) Azure Function and replies to the
sender with the verdict. Failures are reported back by email, and configured CC addresses are copied
on every reply.

See the feature spec and design in [`specs/001-imap-spam-watcher/`](specs/001-imap-spam-watcher/)
(`spec.md`, `plan.md`, `quickstart.md`, `contracts/`).

## How it works

1. Polls the mailbox for messages (every `POLL_INTERVAL_SECONDS`).
2. Ignores any message whose `From` does not match `WHITELIST_REGEX` (and its own replies).
3. Extracts the content to classify — the attached original `.eml` if present, otherwise the body.
4. Calls the detector (`x-functions-key` + `x-openai-api-key` headers, `text/plain` body) with a
   bounded retry on transient failures.
5. Replies to `Reply-To` (else `From`) with an HTML + plain-text verdict, or a content-safe error.
6. Permanently expunges the message only after the response is sent.

Content is handled in memory only and never written to disk or logs; secrets are never logged.

## Configuration

All settings come from environment variables (validated at startup — the container fails fast on
invalid config). Copy the template and fill it in:

```bash
cp .env.example .env
```

See [`specs/001-imap-spam-watcher/contracts/configuration.md`](specs/001-imap-spam-watcher/contracts/configuration.md)
for every variable and its validation rules.

## Run (Docker)

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

The service is deployed with `restart: unless-stopped` so it always runs and recovers automatically.

## Develop & test

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # (Linux/macOS: .venv/bin/pip)
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m pytest
```

End-to-end validation scenarios are documented in
[`specs/001-imap-spam-watcher/quickstart.md`](specs/001-imap-spam-watcher/quickstart.md); the
`tests/integration` suite exercises the same flows in-process.

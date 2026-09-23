# Feature Specification: IMAP Spam Watcher

**Feature Branch**: `001-imap-spam-watcher`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "A mail watcher application for an IMAP mail account, running in a Docker container. A whitelisted user forwards an email to this email address. This script will then pick up this text and make an API call to the spam-detector app (https://github.com/Soneritics/spam-dectector), documented in spam-detector-swagger.json. The app runs as an Azure Function using function authentication, so an `x-functions-key` header must be sent. The result is sent back to the original sender, optionally CC'ing configured addresses. When processing is not possible due to errors, the error is sent as the email body. The container must always run (restart: unless-stopped). Configuration: incoming and outgoing mail server host/port/username/password, whitelist sender regex, semicolon-separated CC list, spam detector URL, and functions key."

## Clarifications

### Session 2026-09-23

- Q: How should the watcher track processed messages to guarantee exactly-once and restart recovery? → A: Delete each message from the mailbox after its reply/error notification has been successfully sent (no local persistence required).
- Q: How many times should a transient detector failure be retried before the sender is emailed an error? → A: Bounded retry — up to ~3 attempts over roughly 1–2 minutes, then send the error notification (deterministic content-rejection errors are not retried).
- Q: What operational logging should the watcher emit? → A: Structured per-message outcome logs (received → whitelisted/ignored → verdict or error → send result, with timing) plus startup and connectivity events, never logging secrets or full message content.
- Q: Should the watcher rate-limit classification requests to control OpenAI cost/abuse? → A: No rate limiting in v1 — rely on the trusted-sender whitelist and modest volume (may be added later).
- Q: What form should the verdict reply email take? → A: HTML-formatted email (verdict visually emphasized / color-coded) with a plain-text fallback, listing verdict, confidence, reason, prompt-injection status, and which content (attached original vs. body) was evaluated.
- Q: Which address is authoritative for whitelist matching and reply routing? → A: Match the whitelist against the From-header address; send the reply/notification to the Reply-To address when present, otherwise to the From-header address.
- Q: How is From-header spoofing of whitelisted senders mitigated? → A: Rely on the receiving mail provider's upstream SPF/DKIM/DMARC enforcement; the watcher matches only the From address and treats surviving spoofed mail as an accepted residual risk in v1 (documented).
- Q: What may an error-notification email contain? → A: A human-readable failure description, the detector's returned error message, and a non-sensitive failure category — never secrets/credentials, original message content, or raw stack traces/internal diagnostics.
- Q: How is the sensitive forwarded email content handled and retained? → A: Processed only in memory; never written to disk/temp files or logs; retained only for the duration of processing; processed messages permanently expunged from the mailbox (not left in Trash).
- Q: Is TLS required for IMAP, SMTP, and the detector call? → A: TLS is preferred and used whenever the server/endpoint supports it; an unencrypted fallback is permitted when a server does not support TLS (accepted residual risk — operators are advised to use TLS-capable servers).
- Q: Should the spec document the third-party data flow (content sent to the external detector + OpenAI) as a privacy disclosure/consent item? → A: No — intentionally omitted for v1; no data-flow/privacy disclosure or consent requirement is added.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a spam verdict for a forwarded email (Priority: P1)

An authorized (whitelisted) user receives a suspicious email in their own inbox and wants to know whether it is spam. They forward that email to the monitored mailbox. The watcher picks up the message, submits its content to the spam detector, and replies to the sender with a clear verdict (spam or not spam), a confidence level, the reason for the verdict, and whether a prompt-injection attempt was detected.

**Why this priority**: This is the core value of the feature. Without it, nothing else matters — the entire purpose is to turn a forwarded email into an actionable spam verdict delivered back to the requester.

**Independent Test**: Configure the mailbox and detector, forward a known email from a whitelisted address, and confirm a reply containing a classification verdict arrives at the sender's address. Delivers standalone value even without CC or advanced error handling.

**Acceptance Scenarios**:

1. **Given** a whitelisted user forwards an email to the monitored mailbox, **When** the watcher processes it and the detector classifies it as spam, **Then** the sender receives a reply stating the message is spam, including confidence, reason, and prompt-injection status.
2. **Given** a whitelisted user forwards a legitimate email, **When** the detector classifies it as not spam, **Then** the sender receives a reply stating the message is not spam, with the accompanying details.
3. **Given** multiple whitelisted emails arrive close together, **When** the watcher processes them, **Then** each email receives its own separate reply with its own verdict.

---

### User Story 2 - Only authorized senders are served (Priority: P2)

The mailbox must only act on requests from approved senders. When an email arrives from an address that does not match the configured whitelist pattern, the watcher ignores it entirely — it is not classified and no reply is sent — so the service cannot be used by unauthorized parties or turned into a reflector for unsolicited replies.

**Why this priority**: Security and abuse-prevention boundary. Processing arbitrary senders would leak detector usage, incur cost, and risk sending replies to spoofed or unwilling third parties. Important, but the feature can be demonstrated for a trusted sender before this is hardened.

**Independent Test**: Send an email from an address that does not match the whitelist regex and confirm no classification occurs and no reply is generated; then send from a matching address and confirm normal processing.

**Acceptance Scenarios**:

1. **Given** an email from a sender that does not match the whitelist pattern, **When** the watcher inspects it, **Then** the email is ignored with no classification call and no reply.
2. **Given** an email from a sender that matches the whitelist pattern, **When** the watcher inspects it, **Then** the email proceeds to classification.

---

### User Story 3 - Receive a clear explanation when processing fails (Priority: P2)

When the watcher cannot complete a classification for a whitelisted request — for example, the detector is unreachable, returns an error, or the content is rejected — the sender still receives an email. Instead of a verdict, the body explains that processing was not possible and describes the error, so the requester is never left without a response.

**Why this priority**: Ensures the requester always gets a definitive outcome. This turns silent failures into actionable feedback, but depends on the P1 happy path existing first.

**Independent Test**: Point the watcher at an unavailable or failing detector endpoint, forward a whitelisted email, and confirm the sender receives an email whose body describes the failure rather than a verdict.

**Acceptance Scenarios**:

1. **Given** a whitelisted email is being processed, **When** the spam detector returns an error or is unreachable, **Then** the sender receives an email whose body describes that processing failed and why.
2. **Given** a whitelisted email cannot be processed for any reason, **When** the failure occurs, **Then** the sender receives exactly one notification and the message is not left unacknowledged or endlessly retried into duplicate replies.

---

### User Story 4 - Keep configured recipients informed via CC (Priority: P3)

An operator can configure a list of CC addresses. When enabled, every classification reply (and error notification) is also copied to those addresses, giving a security team or shared mailbox visibility into what is being checked and the outcomes, without the requester having to forward results manually.

**Why this priority**: A convenience/oversight enhancement. Valuable for teams, but the core request-and-reply loop works without it.

**Independent Test**: Configure one or more CC addresses, forward a whitelisted email, and confirm both the sender and all configured CC addresses receive the reply. Then clear the CC configuration and confirm only the sender is addressed.

**Acceptance Scenarios**:

1. **Given** one or more CC addresses are configured, **When** a reply is sent, **Then** the sender and every configured CC address receive the message.
2. **Given** no CC addresses are configured, **When** a reply is sent, **Then** only the original sender receives the message.
3. **Given** a semicolon-separated CC list with surrounding whitespace or a trailing separator, **When** the reply is addressed, **Then** each valid address is included and empty entries are ignored.

---

### Edge Cases

- **Forwarded content shape**: A forwarded message may contain the original email inline (quoted with forwarding headers), as an attachment, in HTML only, or in plain text. The content that gets classified must be well defined (see FR-004).
- **Empty or oversized content**: If the extracted content is empty (including a whitelisted message with no body and no attachment) or exceeds the detector's maximum allowed size, the request would be rejected by the detector; the sender must receive an error notification rather than silence (empty content is handled as a deterministic error, without a detector call).
- **Non-whitelisted sender**: Ignored entirely (no classification, no reply) — see User Story 2.
- **Malformed / unparseable message**: A message the watcher cannot read (encoding issues, corrupt MIME) should result in an error notification to the sender where the sender is identifiable, and otherwise be skipped without crashing the watcher.
- **Mail server unavailable**: If the incoming server is temporarily unreachable, the watcher must keep retrying and resume when connectivity returns, without losing unprocessed messages. If the outgoing server is unavailable, the reply must be retried rather than dropped.
- **Duplicate delivery / restart mid-processing**: A message is deleted only after its reply/error notification has been sent, so a message that failed before any response was sent remains in the mailbox and is retried on restart. A crash in the narrow window between sending the response and deleting the message could produce a single duplicate reply on restart; this is the accepted trade-off for avoiding a persistent processed-state store.
- **Prompt injection in forwarded content**: The forwarded email may itself attempt prompt injection; the detector reports this, and the verdict conveyed to the sender must surface that fact.
- **Reply loops**: A reply or error notification must not itself be re-ingested and re-processed by the watcher (e.g., if the monitored mailbox also receives copies).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST continuously monitor the configured incoming mailbox, treating every message currently present in the mailbox as a pending request to be processed (a message remains "pending" until it has been processed and expunged per FR-011).
- **FR-002**: System MUST evaluate each incoming message's From-header address against a configurable whitelist pattern. Matching applies the configured regular expression to the email address portion of the From header (excluding any display name), is case-insensitive, and — when the header contains multiple addresses — uses the first address.
- **FR-003**: System MUST ignore any message whose sender does not match the whitelist pattern — performing no classification and sending no reply.
- **FR-004**: System MUST extract the email content to be classified from each whitelisted message. When the forwarded message includes an attached original message (e.g., an `.eml`/message attachment), System MUST classify that attached original; when no such attachment is present, System MUST classify the received message's textual body. When multiple attached original messages are present, System MUST classify the first such attachment in MIME order. When a whitelisted message contains neither an attached original message nor any textual body, System MUST treat its content as empty (handled as a deterministic error per FR-010).
- **FR-005**: System MUST submit the extracted content to the configured spam detector service as a `text/plain` request body and include the required function authentication credential (`x-functions-key`) on the request.
- **FR-006**: System MUST provide the OpenAI API key that the spam detector requires (sent as the `x-openai-api-key` header) and MUST support an optional model override, both supplied via container configuration.
- **FR-007**: System MUST send the classification result to the message's Reply-To address when one is present, otherwise to its From-header address.
- **FR-008**: The reply MUST be an HTML-formatted email with a plain-text fallback (for clients that cannot render HTML) that clearly conveys the outcome: whether the content is spam, the confidence level expressed as a percentage (0–100%), the reason given, whether prompt injection was detected, and which content was evaluated (the attached original message or the received body). The spam / not-spam outcome MUST be conveyed in text and MUST NOT rely on color alone; color or other visual emphasis is an additional aid. The subject MUST reference the original message so the requester can correlate it (subject format and language per FR-019).
- **FR-009**: System MUST optionally include a configurable, semicolon-separated list of CC addresses on every outgoing reply and error notification, ignoring empty entries and surrounding whitespace.
- **FR-010**: When classification cannot be completed for a whitelisted message, System MUST send an email to the original sender (its Reply-To address when present, otherwise its From-header address) whose body describes the error. Transient detector failures (timeout, connectivity, or 5xx) MUST be retried up to a configurable maximum number of attempts (default 3) using exponential backoff with jitter, bounded to a configurable total retry window (default 90 seconds) before the error notification is sent; deterministic failures (e.g., empty, oversized, or rejected content) MUST produce an error notification without retrying. Responses with unexpected or undocumented status codes MUST be treated as transient failures for retry purposes. The error-notification body MUST be limited to a human-readable failure description, the detector's returned error message, and a non-sensitive failure category; it MUST NOT include secrets or credentials, the original message content, or raw stack traces / internal diagnostics.
- **FR-011**: System MUST process each qualifying message exactly once under normal operation, producing exactly one reply or error notification per message. To prevent reprocessing, System MUST permanently delete (expunge) each message from the mailbox only after its reply or error notification has been successfully sent; because deletion follows sending, no local persistence is required, and any message not yet fully processed remains in the mailbox to be retried after a restart.
- **FR-012**: System MUST run continuously and automatically resume operation after failures or restarts without manual intervention (deployment configured with an always-restart policy).
- **FR-013**: System MUST be configurable, via container configuration, for at least: incoming mail server host, port, username, and password; outgoing mail server host, port, username, and password; whitelist sender pattern; CC address list; spam detector URL; spam detector functions key; spam detector OpenAI API key; an optional spam detector model override; the mailbox polling interval (default 45 s); and the detector retry maximum attempts (default 3) and retry window (default 90 s).
- **FR-014**: System MUST NOT log or otherwise persist sensitive credentials or API keys (mail passwords, functions key, and any provider key).
- **FR-015**: System MUST avoid processing its own outgoing replies/error notifications as new inbound requests (no self-reply loops).
- **FR-016**: System MUST tolerate transient outages by retrying: transient spam-detector failures are retried per the bounded policy defined in FR-010; outgoing mail-server failures are retried on subsequent polls until the server recovers (since no notification can be sent meanwhile). System MUST NOT lose unprocessed inbound messages or silently drop outgoing replies.
- **FR-017**: System MUST emit structured operational logs covering startup, mail-server and detector connectivity events, and the outcome of each processed message (received, whitelisted or ignored, classification verdict or error, and send result) with timing — without logging secrets or full message content. Each per-message log record MUST include at least: a message identifier, the sender address, the subject, the decision (ignored / classified / error), the verdict and confidence when classified, the error category when failed, and processing timing.
- **FR-018**: System MUST process email content and attachments only in memory: it MUST NOT write message content or attachments to disk or temporary files, MUST NOT include them in logs, and MUST NOT retain them beyond the processing of that message. Processed messages MUST be permanently removed (expunged) from the mailbox rather than left in a Trash or otherwise recoverable folder.
- **FR-019**: All outgoing messages (verdict replies and error notifications) MUST use a subject of the form `Spam check: <original subject>` and MUST be written in a single default language (English for v1).
- **FR-020**: System MUST treat the detector response as a failure — routing it to the error-notification path — when the HTTP status is unsuccessful or the response envelope indicates an error (`isError = true`); only a successful status with `isError = false` yields a verdict reply.
- **FR-021**: System MUST validate all configuration at startup and, if any required setting is missing or invalid (including an uncompilable whitelist pattern or malformed CC, URL, or port values), MUST log a clear error identifying the offending setting and exit without beginning to poll; validation errors MUST NOT echo secret values.

### Key Entities *(include if feature involves data)*

- **Incoming Request Email**: A message received in the monitored mailbox. Key attributes: sender address, subject, content/body (and any attachments), received timestamp. The message is permanently expunged from the mailbox once its response has been sent, so processed state is represented by absence rather than a stored flag.
- **Sender Whitelist Rule**: The configured pattern that determines which sender addresses are authorized. Key attribute: the matching pattern.
- **Classification Result**: The outcome returned by the spam detector. Key attributes: spam (yes/no), confidence level, reason, prompt-injection-detected flag, and error indicator/message when applicable.
- **Reply / Notification Email**: The message sent back to the requester. Key attributes: recipient (original sender), CC recipients, subject (references the original message), and body. Verdict replies are HTML-formatted with a plain-text fallback and state the spam/not-spam outcome in text, additionally visually emphasized (e.g., color-coded); error notifications carry a non-sensitive description of the failure.
- **Configuration**: The operator-supplied settings governing behavior. Key attributes: incoming mail server connection details, outgoing mail server connection details, whitelist pattern, CC list, detector URL, detector functions key, detector OpenAI API key, optional detector model override, mailbox polling interval, and detector retry settings (maximum attempts and retry window).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A whitelisted user who forwards an email receives a reply containing a clear spam/not-spam verdict within 2 minutes under normal operating conditions.
- **SC-002**: 100% of messages from senders that do not match the whitelist are ignored — no classification is performed and no reply is sent.
- **SC-003**: Under normal operation, 100% of whitelisted messages result in exactly one outbound response — either a verdict or an error notification — with no duplicates and none left unacknowledged.
- **SC-004**: When the spam detector is unavailable or returns an error, 100% of affected whitelisted senders receive an email describing the failure — after up to ~3 retry attempts over ~1–2 minutes for transient errors, or without delay for deterministic content-rejection errors.
- **SC-005**: A user reading a reply can determine the spam/not-spam outcome, its confidence, the reason, and whether prompt injection was detected, without needing any additional context or tooling.
- **SC-006**: The service resumes monitoring automatically after a crash or restart and processes messages that arrived during downtime, with no manual intervention required.
- **SC-007**: When CC addresses are configured, 100% of outgoing replies and error notifications are also delivered to every configured CC address; when none are configured, only the sender is addressed.
- **SC-008**: For every processed message, an operator can trace its outcome (ignored, verdict delivered, or error) from the logs alone, without any secrets or full message content being exposed in those logs.
- **SC-009**: No email content or attachments are written to disk or logs at any point during processing, and processed messages are permanently expunged from the mailbox — verifiable by inspecting the container filesystem and logs and the mailbox after processing.

## Assumptions

- **Whitelist matching**: The whitelist is a single configurable pattern (regular expression) matched against the message's From-header address; a non-match means the message is silently ignored (no bounce, no reply), which is the safe default against abuse and reply reflection.
- **Sender authenticity**: Sender verification relies on the receiving mail provider's upstream SPF/DKIM/DMARC enforcement — messages failing those checks are expected to be rejected or quarantined before reaching the monitored mailbox. The watcher matches only the From-header address and does not independently verify authentication results, so a forged From address that survives upstream filtering is an accepted residual risk in v1 (its impact is bounded: replies are sent to the impersonated whitelisted address rather than to an attacker, and cost/abuse are limited by the trusted whitelist).
- **Message acquisition**: The watcher polls the monitored mailbox on a recurring interval and treats messages present in the mailbox as pending work. After a message's reply/error notification is successfully sent, the message is permanently removed (expunged) from the mailbox to prevent reprocessing; no local processed-state store is kept. A short polling interval (on the order of a minute or less) is acceptable for the 2-minute reply target.
- **Reply addressing**: Replies are sent to the received message's Reply-To address when present, otherwise its From-header address. The reply subject references the original message (e.g., a "Re:"/result-style subject) so the requester can correlate it.
- **Content sent to the detector**: The detector accepts the raw email body as plain text. When the forwarded message carries the original as an attached message (`.eml`/message attachment), the watcher classifies that attached original; otherwise it sends the textual body of the received message.
- **Detector credentials**: The detector requires both the function authentication key (`x-functions-key`) and an OpenAI API key (`x-openai-api-key`, bring-your-own-key); both are mandatory container configuration, with an optional model override (`x-openai-model`).
- **Single mailbox / single detector**: One monitored mailbox and one spam detector endpoint are configured per running container instance.
- **Credential delivery**: All secrets and connection settings are supplied through container configuration (environment/secret configuration) rather than hard-coded, and are never written to logs.
- **Transport security**: TLS is used for IMAP, SMTP, and the detector connection whenever the server/endpoint supports it (implicit TLS or STARTTLS on the configured mail ports; HTTPS for the detector URL). When a mail server does not support TLS, the watcher MAY fall back to an unencrypted connection; because that fallback transmits credentials and message content in plaintext, operators are strongly advised to use TLS-capable servers, and use of the plaintext fallback is an accepted residual risk.
- **Volume**: Request volume is modest (interactive, human-forwarded emails), so no high-throughput or horizontal-scaling design is required for the initial version.
- **Out of scope (initial version)**: A management UI, historical reporting/dashboards, multi-mailbox support, multi-tenant whitelists, rate limiting / per-request cost caps, and automated retraining of the detector are not included. Cost and abuse are controlled solely by the sender whitelist in v1.

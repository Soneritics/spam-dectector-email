# Contract: Email Interface (inbound request & outbound response)

This application's primary external interface is email. This contract defines what a valid inbound request looks like and what the outbound responses must contain.

## Inbound: forwarded request email

| Aspect | Contract |
|--------|----------|
| Delivery | Arrives in the monitored IMAP mailbox |
| Authorization | The `From`-header address MUST match the configured `whitelist_regex`; otherwise the message is ignored entirely (no classification, no reply) — FR-002/FR-003 |
| Content to classify | If the message contains an attached original message (`message/rfc822` part, or attachment with `.eml` filename / `message/rfc822` type), its text is classified; otherwise the received body (`text/plain` preferred, else stripped `text/html`) — FR-004 |
| Reply target | `Reply-To` when present, else `From` — FR-007 |

Edge conditions:
- Empty extracted content → deterministic error notification (no detector call retry).
- Unparseable/corrupt MIME → error notification when the reply target is identifiable, otherwise skipped without crashing.

## Outbound: verdict reply

| Aspect | Contract |
|--------|----------|
| Format | `multipart/alternative` with both `text/html` and `text/plain` parts — FR-008 |
| To | Reply target (above) |
| Cc | Configured `cc_addresses` (empty when unset); `;`-separated parsing, whitespace/empty entries ignored — FR-009 |
| Subject | References the original subject (e.g., `Spam check: <original subject>`) |
| Identifying header | Includes `X-Spam-Watcher: reply` to prevent self-reprocessing — FR-015 |
| Body fields | Spam verdict (visually emphasized / color-coded in HTML), confidence, reason, prompt-injection status, and which content was evaluated (attached original vs. body) — FR-008 |

Plain-text part MUST convey the same verdict information for non-HTML clients.

## Outbound: error notification

| Aspect | Contract |
|--------|----------|
| Trigger | Classification could not be completed (deterministic error, or transient error after retries exhausted) — FR-010 |
| To / Cc / Subject / header | Same addressing, CC, and identifying-header rules as the verdict reply |
| Body | Human-readable description of the failure (derived from the detector `errorMessage` or the failure category). MUST NOT include secrets or full message content — FR-014 |

## Delivery guarantees

- Exactly one outbound response (verdict **or** error) per whitelisted message under normal operation — FR-011, SC-003.
- The source message is deleted only after its response is successfully sent — FR-011.

## Contract test expectations

- Non-whitelisted `From` ⇒ zero outbound messages, zero detector calls.
- Whitelisted message with a `.eml` attachment ⇒ classified content equals the attached original's text.
- Verdict reply is multipart with both parts and carries all required fields + the identifying header.
- CC list `"a@x.com; ;  b@y.com "` ⇒ recipients `a@x.com`, `b@y.com`.
- A message the watcher itself sent (identifying header present / non-whitelisted From) is not reprocessed.

# Contract: Spam Detector API (consumed)

The watcher is a **consumer** of the external Spam Detector Azure Function. This contract is derived from `spam-detector-swagger.json` and pins the request shaping and response handling the watcher must implement.

## Endpoint

- **Method / Path**: `POST {detector_url}` where `detector_url` targets `/spam-check/email`.
- **Auth**: Azure Function authentication via header (see below). No query auth.

## Request

| Part | Value |
|------|-------|
| Header `x-functions-key` | Azure Function key (`detector_functions_key`) — **required** |
| Header `x-openai-api-key` | Bring-your-own OpenAI API key (`detector_openai_key`) — **required** by the API |
| Header `x-openai-model` | Optional model override (`detector_model`) — sent only when configured |
| Header `Content-Type` | `text/plain` |
| Body | The raw email content to classify (`IncomingRequest.content_to_classify`), as plain text — **never** JSON-encoded |

Notes:
- The body is the extracted content: the attached original message's text when present, otherwise the received body (FR-004).
- Secrets in headers must never be logged (FR-014).

## Response envelope: `apiResult_spamResult`

```json
{
  "result": {
    "spam": true,
    "confidence": 0.0,
    "promptInjectionDetected": false,
    "reason": "string"
  },
  "httpCode": 200,
  "isError": false,
  "errorMessage": "string"
}
```

## Status-code handling (drives retry vs. notify)

| Status | Meaning (per schema) | Watcher behavior |
|--------|----------------------|------------------|
| `200` | Classification result | If `isError == false`: build verdict reply from `result`. If `isError == true`: treat as failure → error notification. |
| `400` | Missing key header or empty body | **Deterministic** — no retry; send error notification. |
| `413` | Body exceeds max size | **Deterministic** — no retry; send error notification. |
| `502` | Upstream provider failure | **Transient** — retry (≤ `retry_max_attempts` within `retry_window_seconds`), then error notification. |
| `500` | Unexpected server error | **Transient** — retry, then error notification. |
| connection error / timeout | Network/unreachable | **Transient** — retry, then error notification. |

## Field mapping to the reply

| Response field | Reply usage |
|----------------|-------------|
| `result.spam` | Verdict (spam / not spam), visually emphasized |
| `result.confidence` | Confidence (rendered as % or 0–1) |
| `result.reason` | Reason text |
| `result.promptInjectionDetected` | Prompt-injection warning flag |
| `errorMessage` | Included in error notifications only |

## Contract test expectations

- Request is `POST` with `Content-Type: text/plain` and a non-empty text body.
- Headers `x-functions-key` and `x-openai-api-key` are always present; `x-openai-model` present iff configured.
- A `200` + `isError=false` payload yields a verdict reply with all four `result` fields.
- `400`/`413` yield an immediate error notification (asserts **no** retry).
- `502`/`500`/timeout trigger bounded retries then an error notification.

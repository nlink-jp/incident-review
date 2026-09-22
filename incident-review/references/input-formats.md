# Input formats accepted by preprocess.py

The skill's input is the incident's *communication record*, however it
exists — an export file, a plain-text log, a channel readable through a
connector, a pasted conversation. Acquisition (SKILL.md Phase 0) turns it
into a file; `scripts/preprocess.py` then auto-detects one of four
formats. Anything not natively readable must first be converted —
mechanically, verbatim, without summarizing — into the generic transcript
format below. Records acquired through a connector (e.g. a
Slack-channel-reading tool) are likewise materialized into the generic
transcript format, copying timestamps, author names, and text exactly as
the system returns them.

## 1. Slack export (scat / scli) — single JSON object

The shared export schema of the nlink-jp Slack tools:

```json
{
  "export_timestamp": "2026-07-10T18:00:00+09:00",
  "channel_name": "#incident-example",
  "messages": [
    {
      "user_id": "U012345",
      "user_name": "alice",
      "post_type": "user",
      "timestamp": "2026-07-10T09:15:00+09:00",
      "timestamp_unix": "1783980900.000100",
      "text": "...",
      "files": [],
      "attachments": [],
      "blocks": [],
      "is_reply": false
    }
  ]
}
```

Detected by the presence of `channel_name`. Required per message:
`user_id`, `post_type` (`user` | `bot`), `timestamp`. When `text` is
empty, content is recovered from legacy `attachments`
(pretext/title/text/fallback) and Block Kit `blocks`, in that order —
same fallback ai-ir2 used.

Field notes from the writing tools: `channel_name` carries the `#`,
`files` is always present (possibly empty), `thread_timestamp_unix` is
omitted when the message is not in a thread, and `text` is the raw API
text with mentions left as `<@U…>`. scat and scli group replies under
their parent, so messages are not in strict time order; stail's NDJSON
is in page order and omits `local_path`.

## 2. Slack export (stail) — NDJSON

One message object per line (same message schema as above). The record
name is taken from the file stem and the record timestamp from the latest
message timestamp.

## 3. Generic transcript — any other record

For ticket threads, other-platform chats, or timeline notes, convert to:

```json
{
  "record_name": "INC-2026-042 response thread",
  "record_timestamp": "2026-07-10T18:00:00+09:00",
  "messages": [
    {
      "timestamp": "2026-07-10T09:15:00+09:00",
      "author": "alice",
      "text": "...",
      "post_type": "user",
      "is_reply": false
    }
  ]
}
```

Detected by the presence of `record_name`. Required per message:
`timestamp`, `author`, `text`. Optional: `post_type` (default `user`;
use `bot` for automated posters), `is_reply` (default `false`),
`record_timestamp` (defaults to the latest message timestamp).

## 4. Plain-text conversation log

A `.txt`-style record (chat copy-paste, hand-kept log). Any non-JSON file
lands here. Parsing is line-based and deterministic:

```
[2026-07-10T09:15:00+09:00] alice: 不審なログイン試行を検知
2026-07-10 09:20 bob: アカウントをロックしました
続きの行はそのまま前のメッセージに連結される
carol: タイムスタンプ無しの発言も可
```

- A new message starts at `[timestamp] author: text` or `author: text`
  (timestamp optional, `[]` optional, half- or full-width colon;
  timestamps are `YYYY-MM-DD` optionally followed by a time).
- Any other non-empty line continues the previous message (lines starting
  with a URL scheme are always continuations, so `https://…` is never
  misread as an author).
- Leading lines before the first `author:` line get author `unknown`.
- The record name comes from the file stem; the record timestamp from the
  latest parsed timestamp.

The parser is a heuristic for well-formed logs. If your text doesn't fit
this shape (multi-line headers, interleaved formats), convert it to the
generic transcript format instead — that is always the safe route.

Conversion rules:

- Copy text verbatim — do not paraphrase, translate, defang, or omit
  messages. Defanging is preprocess.py's job, on the whole record,
  deterministically.
- Timestamps: keep the source's precision, formatted ISO 8601 where
  possible. If the source shows only times, prefix the known date. If
  ordering is all you have, use sequence-preserving timestamps and say so
  in the final report.
- `author` is the name as it appears in the source.

# incident-review

Claude Code Skill that retrospectively analyzes your own organization's IR
communication record — a Slack export (scat/stail/scli), a plain-text
conversation log, a channel read live through a connector, or any
conversation/timeline record — and produces a schema-validated JSON report
(summary, per-participant activity, role inference, process-quality
review) plus reusable investigation-tactic knowledge documents. Invoked as
`/incident-review <record>`.

Successor to the [ai-ir](https://github.com/nlink-jp/ai-ir) /
[ai-ir2](https://github.com/nlink-jp/ai-ir2) CLIs, and companion to
[incident-research](https://github.com/nlink-jp/incident-research): that
skill researches *someone else's public* incident from the web; this one
reviews *your own* incident from its internal record, with zero contact
with anything the record mentions. Three
design points carry the weight (design:
[ADR-009](https://github.com/nlink-jp/.github/blob/main/adr/009-incident-review-skill.md)):

- **A mandatory preprocessing gate** — the analyzing agent never reads the
  raw record. `preprocess.py` defangs every IoC, wraps every message in
  nonce-tagged isolation blocks (attacker-quoted content is data, never
  instructions), flags injection-suspect messages, and normalizes any input
  shape into one transcript form.
- **Generalized input** — the unit of input is the communication record,
  not a file format. Slack exports, NDJSON streams, and plain-text logs
  are read natively; records living in connected systems (e.g. a Slack
  channel readable through an MCP connector) are acquired and
  materialized verbatim; everything else enters via a small documented
  generic-transcript format.
- **Evidence-disciplined knowledge** — extracted tactics carry
  `confirmed`/`inferred`/`suggested` confidence (`confirmed` only when
  output was actually shared in the record), with the field set kept
  compatible with ai-ir2's knowledge documents.

The skill itself performs no web access: it never fetches URLs and never
contacts any host mentioned in the record — IoC enrichment is a separate,
deliberate step outside this skill. Note that the analysis runs in your
Claude session, so the preprocessed (defanged, nonce-isolated) record is
sent to the model backend powering the session, like any other session
content; nothing goes anywhere else.

## Install

From a release zip (also uploadable as-is to claude.ai → Settings → Skills):

```bash
unzip incident-review-vX.Y.Z.zip -d ~/.claude/skills/
```

From a checkout:

```bash
make install
```

Requirements: Claude Code and `python3` (3.9+, stdlib only) for the bundled
preprocess/validation/compile scripts. No API keys, no cloud project — the
Vertex AI dependency of ai-ir2 is gone.

## Usage

```
/incident-review incident-export.json
/incident-review ticket-thread.json --lang en
```

Produces in `./reports/`, after a preprocess → per-section analysis
(summary / activity / roles / review / tactics) → validate → compile
workflow:

- `<incident_id>_<date>.json` — structured report (schema:
  `incident-review/schema.json`, semantics:
  `incident-review/references/report-format.md`)
- `<incident_id>_<date>.md` — human-readable report (self-contained HTML
  with `--format html`)
- `knowledge/<tactic-id>-<slug>.md` — one RAG-ready knowledge document per
  extracted tactic

Reports default to Japanese; `--lang en` switches every field and label to
English. Fields the record doesn't support say `不明` / `unknown` — never a
guess. Retrospective only: live analysis during an ongoing incident and
cross-incident trends are out of scope.

## Development

| Command | Purpose |
|---------|---------|
| `make check` (= `make test`) | Structural validation + script behaviour tests |
| `make install` | Copy the skill to `~/.claude/skills/incident-review` |
| `make package` | Build `dist/incident-review-vX.Y.Z.zip` (zip root = skill folder) |

## Documentation

- [Input format specification](incident-review/references/input-formats.md)
- [Report format specification](incident-review/references/report-format.md)
- [ADR-009 — design decision record](https://github.com/nlink-jp/.github/blob/main/adr/009-incident-review-skill.md)
- [日本語ドキュメント](README.ja.md)

## Notes

- The review reflects only what the record contains — undocumented work is
  invisible to it.
- All IoCs in every output are defanged (`hxxps`, `[.]`); reports are safe
  to share and index.
- The record is treated as confidential: outputs stay in the local report
  directory, and record content reaches nothing beyond the model backend
  that powers your Claude session.

## License

MIT

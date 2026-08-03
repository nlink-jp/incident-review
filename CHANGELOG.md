# Changelog

## [Unreleased]

### Changed

- The design record for this skill moved out of the organization ADR log
  into `docs/{en,ja}/adr/` (0001 retrospective analysis, formerly
  organization ADR-009), now mirrored in Japanese as well as English. The
  organization log is for decisions that bind the whole organization; the
  old number stays reserved there as a redirect.

## v0.1.1 - 2026-07-31

- docs: correct the "offline" claim — the skill itself performs no web
  access and contacts nothing the record mentions, but analysis runs in a
  Claude session, so the preprocessed record reaches the session's model
  backend like any other session content. README (en/ja), SKILL.md
  security preamble, AGENTS.md, and CLAUDE.md now state the data flow
  precisely instead of claiming "fully offline" / "ローカルで完結"

## v0.1.0 - 2026-07-31

Initial release (ADR-009). Successor to the ai-ir / ai-ir2 CLIs.

- `/incident-review <record-file>` — retrospective analysis of one's own
  incident-response record into a schema-validated JSON report + Markdown /
  self-contained HTML + per-tactic knowledge documents
- Input generalized to "the IR communication record": export files read
  natively, connector-acquired records and anything else via the generic
  transcript format (SKILL.md Phase 0 acquisition routes)
- Mandatory preprocessing gate (`scripts/preprocess.py`): scat/scli JSON,
  stail NDJSON, plain-text conversation logs, and generic-transcript
  loading; IoC defanging; nonce-tagged message isolation;
  injection-suspect flagging (ported from ai-ir2)
- Five analysis sections (summary / activity / roles / review / tactics)
  with per-section validation (`scripts/validate.py --part`)
- `scripts/compile.py`: Japanese/English Markdown and self-contained HTML
  renderers, plus ai-ir2-compatible RAG-ready tactic knowledge documents
  (`--knowledge-dir`)
- No web tools in `allowed-tools`; all outputs defanged
- Tests: vendored structural validation + 35 script behaviour tests over a
  fictitious fixture incident

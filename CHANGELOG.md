# Changelog

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
- Offline by design: no web tools in `allowed-tools`; all outputs defanged
- Tests: vendored structural validation + 35 script behaviour tests over a
  fictitious fixture incident

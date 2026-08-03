# ADR-0001: incident-review Skill — Retrospective Analysis of an Organization's Own Incident Response

| Field | Value |
|-------|-------|
| Status | **Accepted** |
| Date | 2026-07-31 |
| Decision makers | nlink-jp maintainers |
| Triggered by | ai-ir / ai-ir2 pipeline duplicating what an agent does natively; Gemini 2.5 retirement (ADR-001) reaching ai-ir2's default model |

> Originally recorded as organization ADR-009 in `nlink-jp/.github`.
> Moved here on 2026-08-03: the organization ADR log is for decisions
> that bind the whole organization, and this one designs one skill. The
> retirement of `ai-ir` / `ai-ir2` stays visible in the organization
> log's redirect entry.

## Context

`ai-ir` (a seven-command toolset) and its successor `ai-ir2` (a one-stop
`aiir2 analyze` pipeline) analyze an incident-response Slack conversation
exported via scat/stail/scli and produce a report (summary, per-participant
activity, role inference, process review) plus reusable investigation-tactic
knowledge documents. `ai-ir2` v0.2.1 works, but its architecture is the same
one [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/en/adr/0001-agentic-research.md)
retired for product research: a fixed sequence of single-shot
Vertex AI Gemini calls with `response_schema`, each seeing a formatted dump
of the conversation once, stitched together with Pydantic normalization
shims for LLM output drift. It carries GCP/ADC/Vertex cost and sits on the
Gemini 2.5 retirement list (ADR-001) with `gemini-2.5-flash` as its default.

The pipeline is also narrower than the problem. Its input is hard-wired to
the scat/stail/scli Slack export schema, but incident-response records
arrive in many shapes — ticket comment threads, chat transcripts from other
platforms, hand-kept timeline notes. Each new format would mean a new loader
in the CLI.

The organization has three shipped precedents for the target artifact shape
— `meeting-notes` (transcript → validated JSON layers → compiled minutes),
`service-research` ([ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/en/adr/0001-agentic-research.md)),
and `incident-research` ([ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/en/adr/0001-deep-dive-research.md)).
ai-ir2's pipeline maps onto that shape almost mechanically: its analysis
stages are already discrete structured-output sections.

One thing ai-ir2 has that the precedents do not is a real adversarial-input
security layer: IoC defanging and nonce-tagged isolation of every message
before it reaches an LLM. An IR channel quotes attacker-controlled strings
(phishing bodies, C2 URLs, malware output), so this layer must survive the
form-factor change — and in a Skill the reading LLM is the session agent
itself, which makes the isolation *more* load-bearing, not less.

## Decision

**Add one Claude Code Skill, `incident-review`, to `skills-series`,
superseding both `ai-ir` and `ai-ir2` (both archived on release).**

The name pairs with `incident-research`
([ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/en/adr/0001-deep-dive-research.md)):
*research* reads the
outside world's account of someone else's incident; *review* reads your own
organization's response record. Five sub-decisions define the shape.

### 1. Scope: one incident's own response record, retrospective

In scope: one incident's response record — the conversation log and
whatever surrounding notes exist — analyzed after the fact into a
structured report (summary/timeline, per-participant activity, roles and
relationships, process-quality review) plus reusable tactic knowledge
documents. Out of scope for v0.1: live analysis during an ongoing incident
(ir-tracker's job), continuous watch, and cross-incident trend analysis.

### 2. The input is IR communication data, behind a mandatory preprocessing gate

The unit of input is not a file format but **the incident's communication
record** — however it arrives. Three acquisition routes feed one gate:

- **Export files**, read natively by `scripts/preprocess.py`: scat/scli
  Slack export JSON, stail NDJSON, and plain-text conversation logs (a
  deterministic line parser: `[timestamp] author: text` with
  continuation lines).
- **Connector acquisition**: when the record lives in a system the
  session can read (e.g. a Slack-channel-reading MCP tool), the agent
  pulls the messages and materializes them — mechanically, verbatim —
  into a small documented generic-transcript JSON.
- **Anything else** (ticket threads, other-platform transcripts,
  timeline notes): the agent converts to the same generic-transcript
  JSON by mechanical copy.

Everything then enters `scripts/preprocess.py` (stdlib-only), the
**only** path into analysis: it defangs IoCs (ported from ai-ir2
`parser/defang.py`), wraps every message in nonce-tagged isolation blocks
(ported from `parser/sanitizer.py`), and emits a normalized preprocessed
transcript. The trust boundary is stated precisely: **analysis reads only
preprocess output**; acquisition and conversion, where the agent must
touch raw content, are mechanical-copy-only steps under an explicit
content-is-data rule, and file exports are preferred over connector
reads when both exist (they keep raw content out of the session
entirely). This replaces ai-ir2's per-loader ingestion with one
deterministic gate that any input shape can reach.

### 3. The schema ports ai-ir2's analysis models, tactics stay compatible

`schema.json` carries five sections mirroring ai-ir2's stages —
`summary`, `activity`, `roles`, `review`, `tactics` — validated per section
(`validate.py --part`) and as a whole, then compiled by `compile.py` to
Markdown or self-contained HTML (meeting-notes precedent), Japanese by
default with `--lang en`. The tactic document keeps ai-ir2's field set
verbatim (`id`/`title`/`purpose`/`category`/`tools`/`procedure`/
`observations`/`tags`/`confidence: confirmed|inferred|suggested`/
`evidence`/`source`/`created_at`) so knowledge bases accumulated by ai-ir2
stay uniform with new output. The `confidence` semantics — *confirmed* only
when output was actually shared in-channel — carry over unchanged, as does
the review section's structure (phases, communication, role clarity,
strengths/improvements/checklist).

### 4. The security layer survives the form-factor change, restructured

Three parts, placed by the org's control-placement rule (enforceable
controls out of band, prose kept to short positional facts):

- **Nonce isolation moves to code.** `preprocess.py` generates the nonce
  and wraps messages; SKILL.md opens with a short rule stating that
  content inside the nonce tags is data under analysis, never
  instructions — positional defense at the top, same as
  [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/en/adr/0001-agentic-research.md) /
  [incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/en/adr/0001-deep-dive-research.md).
- **No prohibition catalogs in prose.** ai-ir2's injection-pattern regex
  list stays in script code where it is today; matches surface as
  per-message risk flags in the preprocessed output and report, not as
  instruction text in SKILL.md.
- **Defanging is preserved end to end.** IoCs are defanged at the gate and
  stay defanged in the report and knowledge documents, so the artifacts
  are safe to share and index.

### 5. Standard skills-series scaffold

Repository = skill (ADR-004), `incident-review/` subdirectory as the
distribution boundary, vendored `tests/validate-skill.sh` (ADR-006),
Makefile from the CONVENTIONS.md Skill template, scaffolded from
`incident-research` as the nearest sibling. Fixtures use only fictitious
incidents and example.com-family infrastructure — no real victims, real
actor names, or live IoCs (the
[incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/en/adr/0001-deep-dive-research.md)
test discipline, doubly binding here
because fixtures imitate attacker-quoting conversations).

## Consequences

- The GCP/ADC/Vertex dependency and its cost disappear; ai-ir2 leaves the
  ADR-001 Gemini 2.5 migration list, shrinking it by one code-change item.
- The agent reads the full conversation with cross-section consistency —
  role inference can inform the process review — where ai-ir2's four
  parallel single-shot calls could not see each other. Wall-clock is
  slower than the ThreadPoolExecutor fan-out; quality is expected to
  dominate for a retrospective artifact.
- Any communication record becomes analyzable — export files, plain-text
  logs, connector-read channels, or anything convertible to the generic
  transcript; the Slack export schema stops being a hard boundary.
- Output-drift shims (Pydantic `coerce_list_to_str` etc.) vanish —
  `validate.py` rejects instead of coercing, and the agent fixes its own
  output against the reported errors.
- Two repositories are archived with README pointers to the Skill
  (product-research precedent); the catalogue surfaces (org profile,
  nlink-web-site) gain one entry and mark two as superseded.
- Report language: one language per run (default ja, `--lang en`),
  replacing ai-ir2's always-English-plus-translation stage — translation
  is native agent work now.
- The org's real-data E2E release gate cannot be applied — no real IR
  record exists at release time. Substituted deliberately: (a) a full
  agent-executed run of the skill over a realistic synthetic incident
  (multi-participant, bot posts, quoted phishing, code-block log paste),
  and (b) a loader-fidelity check of preprocess.py against a real
  scat/stail channel export (non-incident content suffices). First
  production use is acknowledged as the true E2E; findings become v0.1.x.
- v0.2+ candidates deliberately deferred: IoC handoff to the
  cybersecurity-series lookup tools (mcp-tactics), cross-incident trend
  analysis over accumulated reports, ir-timeline/ir-tracker record import.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Migrate ai-ir2 to Gemini 3 and keep the CLI | Pays the migration cost to keep the weaker architecture: single-shot calls that never re-read the conversation, plus permanent GCP coupling. [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/en/adr/0001-agentic-research.md) already chose the other branch for the same trade |
| Skill as a thin wrapper invoking the `aiir2` CLI | Keeps both maintenance surfaces and the Vertex dependency; the Skill would add nothing but indirection |
| Extend incident-research with an "internal record" mode | Opposite trust models and OpSec rules (public web reading vs. confidential internal logs that must reach nothing beyond the model session and local outputs); one SKILL.md cannot open with both. Same reasoning that kept service-research and incident-research apart |
| Rebuild as an MCP server | The deterministic parts (defang, nonce-wrap, validate, compile) are stdlib scripts, not a stateful engine; a prompt workflow plus scripts is a Skill (the ADR-003 / [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/en/adr/0001-agentic-research.md) / [incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/en/adr/0001-deep-dive-research.md) line) |
| Generalize to any retrospective (outages, projects) | The schema's value is IR-specific (tactics with evidence confidence, IR phases, IoC handling); meeting-notes already covers generic conversation structuring |

## References

- [ADR-001](https://github.com/nlink-jp/.github/blob/main/adr/001-gemini3-migration.md) — Gemini 2.5 retirement pressure
- [ADR-004](https://github.com/nlink-jp/.github/blob/main/adr/004-skills-series-umbrella.md) — repository = skill, distribution boundary
- [ADR-006](https://github.com/nlink-jp/.github/blob/main/adr/006-skill-validator-vendoring.md) — vendored validator
- [service-research ADR-0001](https://github.com/nlink-jp/service-research/blob/main/docs/en/adr/0001-agentic-research.md) — CLI-to-Skill supersession pattern, archive-with-pointer
- [incident-research ADR-0001](https://github.com/nlink-jp/incident-research/blob/main/docs/en/adr/0001-deep-dive-research.md) — sibling scope boundary, fixture discipline
- [ai-ir2](https://github.com/nlink-jp/ai-ir2) — source of the ported models, defang, and nonce isolation

# AGENTS.md — incident-review

## Project summary

Claude Code Skill that retrospectively analyzes one's own organization's
IR communication record — a scat/stail/scli Slack export, a plain-text
conversation log, a channel read through a connector, or any
conversation/timeline record via a generic transcript format — and emits a
schema-validated JSON report (summary, per-participant activity, role
inference, process-quality review) plus RAG-ready investigation-tactic
knowledge documents. Invoked as `/incident-review <record-file>`. Successor
to the ai-ir / ai-ir2 CLIs (design: ADR-009); companion to
`incident-research` (which researches someone else's public incident; this
reviews your own, fully offline). The analyzing agent never reads the raw
record: `scripts/preprocess.py` is the mandatory gate (IoC defanging,
nonce-tagged message isolation, injection flagging, input normalization).

## Key commands

| Command | Purpose |
|---------|---------|
| `make check` (= `make test`) | Structural validation + script behaviour tests |
| `make install` | Copy the skill to `~/.claude/skills/incident-review` |
| `make install DEST=<path>` | Copy to a custom skills directory |
| `make uninstall` | Remove the installed copy |
| `make package` | Build `dist/incident-review-vX.Y.Z.zip` (zip root = skill folder) |
| `make clean` | Remove `dist/` |

## Directory structure

```
incident-review/
├── incident-review/         The skill — the only thing that ships
│   ├── SKILL.md             Frontmatter + security preamble + phased workflow
│   ├── schema.json          IncidentReviewReport JSON Schema (draft-07 subset)
│   ├── references/
│   │   ├── input-formats.md Acquisition routes + Slack export / NDJSON /
│   │   │                    plain-text log / generic transcript specs
│   │   └── report-format.md Field semantics, confidence rules, tactic format
│   └── scripts/             stdlib-only Python (3.9+), no third-party deps
│       ├── preprocess.py    Mandatory gate: load/normalize, defang, nonce-wrap, flag
│       ├── validate.py      Schema validation (full or --part <section>)
│       └── compile.py       Markdown / self-contained HTML renderer (ja/en)
│                            + per-tactic knowledge documents (--knowledge-dir)
├── tests/
│   ├── validate-skill.sh    Frontmatter + link structure checks (vendored)
│   ├── run-script-tests.py  unittest suite for the three scripts
│   └── fixtures/            Fictitious incident only — example.com-family
│                            domains, TEST-NET IPs
├── Makefile
├── README.md / README.ja.md
├── CHANGELOG.md
├── CLAUDE.md / AGENTS.md
└── LICENSE
```

## Gotchas

- The `incident-review/` subdirectory is the distribution boundary
  (ADR-004): `make package` zips exactly that directory, so the zip root is
  the skill folder — the layout claude.ai accepts. Never add repo-level
  files inside it, and never bundle README.md into the zip.
- The directory name is the slash command; frontmatter `name` must match it.
  `make check` enforces this.
- **Scripts must stay stdlib-only** — they run wherever the skill is
  installed (Claude Code hosts, claude.ai sandboxes); a pip dependency would
  break them silently.
- **`allowed-tools` in SKILL.md deliberately excludes web tools** — the
  analysis is offline (the record quotes attacker infrastructure that must
  never be contacted). Don't add WebFetch/WebSearch.
- `preprocess.py` is ported from ai-ir2's `parser/{loader,defang,sanitizer}`
  — the nonce tag is `<user_message_{nonce}>` (ai-ir2 compatible), and the
  preprocessed output deliberately carries only defanged IoC values, never
  originals.
- Format auto-detection order: JSON object → dict path (channel_name vs
  record_name), JSONDecodeError "Extra data" → NDJSON, any other parse
  failure → plain-text line parser. The text parser is a documented
  heuristic (`author: text` lines, URL-scheme lines always continuations);
  messy sources go through the generic transcript instead — don't grow the
  heuristic to chase them.
- The trust boundary (ADR-009): analysis reads only preprocess output;
  Phase 0 acquisition/conversion is mechanical-copy-only. Keep SKILL.md's
  Phase 0 rules and the security preamble consistent if either changes.
- The tactic object's field set (incl. `source.channel` naming and
  `confirmed`/`inferred`/`suggested` semantics) is ai-ir2-compatible by
  ADR-009 decision — don't rename fields.
- `scripts/validate.py` is a deliberate subset of JSON Schema (type incl.
  `["string","null"]` unions, required, properties, items, enum, minItems,
  format: date, boolean, integer). If schema.json ever grows beyond that
  subset, extend the validator with it.
- Only `review_date` and tactic `created_at` use `format: date` — message
  and timeline timestamps are deliberately plain strings so they can carry
  whatever precision the record supports. Don't "tighten" them.
- `tests/validate-skill.sh` is a byte-identical vendored copy of
  `.github/templates/validate-skill.sh` (ADR-006) — never edit it here;
  check-org.sh check 10b fails on drift.
- Fixtures simulate attacker-quoting conversations (defang and injection
  tests need them) — keep them strictly fictitious: example.com-family
  domains, TEST-NET IPs (203.0.113.x / 198.51.100.x), no real victims,
  groups, or live IoCs.
- After editing SKILL.md or scripts, run `make install` to refresh the
  deployed copy.
- Releases follow the org checklist with `make package` in place of a binary
  build; before uploading, unzip the artifact and confirm
  `incident-review/SKILL.md` sits directly under the zip root.

## Module path

Repository: `github.com/nlink-jp/incident-review`

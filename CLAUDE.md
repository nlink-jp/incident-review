# CLAUDE.md — incident-review

**Organization rules (mandatory): https://github.com/nlink-jp/.github/blob/main/CONVENTIONS.md**

See [`AGENTS.md`](AGENTS.md) for commands, structure, and gotchas.

## Non-negotiable rules

- **Docs in sync** — update `README.md` and `README.ja.md` in the same commit as behaviour changes.
- **Small, typed commits** — `feat:`, `fix:`, `docs:`, `test:`, `chore:`
- **`make check` before committing** — structural validation + script tests are this repo's test suite.
- **The `incident-review/` subdirectory is the distribution boundary** — only
  skill content goes inside it; `make package` ships exactly that directory
  (ADR-004).
- **Bundled scripts are stdlib-only Python** — no third-party dependencies,
  ever; they must run on any host the skill is installed on.
- **The preprocessing gate is the security model** — SKILL.md routes all
  analysis through `preprocess.py` (defang + nonce isolation) and bars web
  tools in `allowed-tools` (nothing the record mentions is ever
  contacted). Keep the security preamble at the top of SKILL.md intact,
  and never describe the skill as "fully offline" — record content still
  reaches the session's model backend.

## Communication Language

All communication between contributors and Claude Code is conducted in **Japanese**.

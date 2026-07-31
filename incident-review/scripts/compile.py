#!/usr/bin/env python3
"""Render an incident-review JSON report (stdlib only).

Usage:
    compile.py report.json -o report.md                      # Markdown, Japanese labels
    compile.py report.json -o report.md --lang en            # English labels
    compile.py report.json -o report.html -f html            # self-contained HTML
    compile.py report.json -o report.md --knowledge-dir knowledge
                                                             # + one Markdown doc per tactic

Tactic knowledge documents keep ai-ir2's RAG-ready layout (one H1, H2
sections, {id}-{slug}.md filenames) so accumulated knowledge bases stay
uniform (ADR-009).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

SCORES = {
    "excellent": ("🟢 非常に良い", "🟢 Excellent"),
    "good": ("🟢 良い", "🟢 Good"),
    "adequate": ("🟡 妥当", "🟡 Adequate"),
    "poor": ("🔴 要改善", "🔴 Poor"),
    "unknown": ("⚪ 不明", "⚪ Unknown"),
}

QUALITIES = {
    "good": ("良い", "Good"),
    "adequate": ("妥当", "Adequate"),
    "poor": ("要改善", "Poor"),
    "unknown": ("不明", "Unknown"),
}

CONFIDENCES = {
    "high": ("高", "High"),
    "medium": ("中", "Medium"),
    "low": ("低", "Low"),
    "confirmed": ("実証済み", "Confirmed"),
    "inferred": ("推定", "Inferred"),
    "suggested": ("提案のみ", "Suggested"),
}

PRIORITIES = {
    "high": ("高", "High"),
    "medium": ("中", "Medium"),
    "low": ("低", "Low"),
}

LABELS = {
    "ja": {
        "title": "インシデント対応レビュー",
        "col_item": "項目",
        "col_value": "内容",
        "review_date": "レビュー日",
        "record": "対象記録",
        "messages": "メッセージ数",
        "severity": "深刻度",
        "score": "総合評価",
        "summary": "## 📝 概要",
        "root_cause": "根本原因",
        "resolution": "解決",
        "affected": "影響システム",
        "timeline": "## 🕒 タイムライン",
        "activity": "## 👥 参加者の活動",
        "roles": "## 🎭 役割と関係",
        "roles_cols": ["参加者", "推定役割", "確度"],
        "evidence": "根拠",
        "relationships": "関係",
        "process": "## 📊 プロセスレビュー",
        "phases_cols": ["フェーズ", "推定所要時間", "品質", "備考"],
        "communication": "コミュニケーション",
        "delays": "遅延",
        "silos": "サイロ",
        "role_clarity": "役割の明確さ",
        "ic_yes": "IC を特定",
        "ic_no": "IC を特定できず",
        "gaps": "空白",
        "overlaps": "重複",
        "tools": "ツール適切性",
        "strengths": "強み",
        "improvements": "改善点",
        "checklist": "次回チェックリスト",
        "checklist_cols": ["項目", "優先度"],
        "tactics": "## 📚 抽出戦術",
        "tactics_none": "この記録からは再利用可能な戦術を抽出できませんでした。",
        "security": "## 🔒 セキュリティノート",
        "flagged": "インジェクション疑いフラグ付きメッセージ",
        "defang_note": "本レポート内の IoC はすべて defang 済み表記です（hxxps, [.] など）。",
        "none": "なし",
    },
    "en": {
        "title": "Incident Response Review",
        "col_item": "Item",
        "col_value": "Value",
        "review_date": "Review date",
        "record": "Record",
        "messages": "Messages",
        "severity": "Severity",
        "score": "Overall score",
        "summary": "## 📝 Summary",
        "root_cause": "Root cause",
        "resolution": "Resolution",
        "affected": "Affected systems",
        "timeline": "## 🕒 Timeline",
        "activity": "## 👥 Participant Activity",
        "roles": "## 🎭 Roles & Relationships",
        "roles_cols": ["Participant", "Inferred role", "Confidence"],
        "evidence": "Evidence",
        "relationships": "Relationships",
        "process": "## 📊 Process Review",
        "phases_cols": ["Phase", "Estimated duration", "Quality", "Notes"],
        "communication": "Communication",
        "delays": "Delays",
        "silos": "Silos",
        "role_clarity": "Role clarity",
        "ic_yes": "IC identified",
        "ic_no": "No IC identified",
        "gaps": "Gaps",
        "overlaps": "Overlaps",
        "tools": "Tool appropriateness",
        "strengths": "Strengths",
        "improvements": "Improvements",
        "checklist": "Checklist for next time",
        "checklist_cols": ["Item", "Priority"],
        "tactics": "## 📚 Extracted Tactics",
        "tactics_none": "No reusable tactics could be extracted from this record.",
        "security": "## 🔒 Security Notes",
        "flagged": "Messages flagged as injection-suspect",
        "defang_note": "All IoCs in this report are written defanged (hxxps, [.] etc.).",
        "none": "none",
    },
}


def pick(table: dict, key: str, lang: str) -> str:
    ja, en = table.get(key, (key, key))
    return ja if lang == "ja" else en


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(report: dict, lang: str) -> str:
    lb = LABELS[lang]
    s = report["summary"]
    rv = report["review"]
    severity = s["severity"] if s["severity"] else ("不明" if lang == "ja" else "unknown")
    lines = [
        f"# {lb['title']}: {s['title']}",
        "",
        f"| {lb['col_item']} | {lb['col_value']} |",
        "|------|------|",
        f"| **Incident ID** | `{report['incident_id']}` |",
        f"| **{lb['review_date']}** | {report['review_date']} |",
        f"| **{lb['record']}** | {report['record_name']} |",
        f"| **{lb['messages']}** | {report['message_count']} |",
        f"| **{lb['severity']}** | {severity} |",
        f"| **{lb['score']}** | {pick(SCORES, rv['overall_score'], lang)} |",
        "",
        "---",
        "",
        lb["summary"],
        "",
        s["summary"],
        "",
        f"- **{lb['root_cause']}**: {s['root_cause']}",
        f"- **{lb['resolution']}**: {s['resolution']}",
    ]
    if s.get("affected_systems"):
        lines.append(f"- **{lb['affected']}**: {', '.join(s['affected_systems'])}")

    lines += ["", lb["timeline"]]
    for e in s["timeline"]:
        lines.append(f"- **{e['timestamp']}** — {e['actor']}: {e['event']}")

    lines += ["", lb["activity"]]
    for p in report["activity"]["participants"]:
        lines += ["", f"### {p['user_name']} — {p['role_hint']}"]
        for a in p["actions"]:
            item = f"- **{a['timestamp']}** {a['purpose']} — {a['method']}"
            lines.append(item)
            if a["findings"]:
                lines.append(f"  - {a['findings']}")

    lines += ["", lb["roles"], ""]
    cols = lb["roles_cols"]
    lines += [
        f"| {cols[0]} | {cols[1]} | {cols[2]} |",
        "|------|------|------|",
    ]
    for p in report["roles"]["participants"]:
        lines.append(
            f"| {p['user_name']} | {p['inferred_role']} | {pick(CONFIDENCES, p['confidence'], lang)} |"
        )
    for p in report["roles"]["participants"]:
        if p["evidence"]:
            lines += ["", f"**{p['user_name']}** — {lb['evidence']}:"]
            lines += [f"- {ev}" for ev in p["evidence"]]
    if report["roles"]["relationships"]:
        lines += ["", f"**{lb['relationships']}:**"]
        for r in report["roles"]["relationships"]:
            target = f" → {r['to_user']}" if r["to_user"] else ""
            lines.append(f"- {r['from_user']}{target} ({r['relationship_type']}): {r['description']}")

    lines += ["", lb["process"], ""]
    if rv["phases"]:
        cols = lb["phases_cols"]
        lines += [
            f"| {cols[0]} | {cols[1]} | {cols[2]} | {cols[3]} |",
            "|------|------|------|------|",
        ]
        for ph in rv["phases"]:
            lines.append(
                f"| {ph['phase']} | {ph['estimated_duration']} | "
                f"{pick(QUALITIES, ph['quality'], lang)} | {ph['notes']} |"
            )
        lines.append("")
    lines.append(f"**{lb['communication']}**: {rv['communication']['overall']}")
    if rv["communication"]["delays_observed"]:
        lines.append(f"- {lb['delays']}:")
        lines += [f"  - {d}" for d in rv["communication"]["delays_observed"]]
    if rv["communication"]["silos_observed"]:
        lines.append(f"- {lb['silos']}:")
        lines += [f"  - {d}" for d in rv["communication"]["silos_observed"]]
    rc = rv["role_clarity"]
    ic = f"{lb['ic_yes']}: {rc['ic_name']}" if rc["ic_identified"] and rc["ic_name"] else (
        lb["ic_yes"] if rc["ic_identified"] else lb["ic_no"]
    )
    lines += ["", f"**{lb['role_clarity']}**: {ic}"]
    if rc["gaps"]:
        lines.append(f"- {lb['gaps']}: {'; '.join(rc['gaps'])}")
    if rc["overlaps"]:
        lines.append(f"- {lb['overlaps']}: {'; '.join(rc['overlaps'])}")
    lines += ["", f"**{lb['tools']}**: {rv['tool_appropriateness']}"]
    if rv["strengths"]:
        lines += ["", f"**{lb['strengths']}:**"] + [f"- {x}" for x in rv["strengths"]]
    if rv["improvements"]:
        lines += ["", f"**{lb['improvements']}:**"] + [f"- {x}" for x in rv["improvements"]]
    if rv["checklist"]:
        cols = lb["checklist_cols"]
        lines += ["", f"**{lb['checklist']}:**", "", f"| {cols[0]} | {cols[1]} |", "|------|------|"]
        for c in rv["checklist"]:
            lines.append(f"| {c['item']} | {pick(PRIORITIES, c['priority'], lang)} |")

    tactics = report["tactics"]
    lines += ["", f"{lb['tactics']} ({len(tactics)})", ""]
    if tactics:
        for t in tactics:
            lines.append(
                f"- **{t['id']}: {t['title']}** ({pick(CONFIDENCES, t['confidence'], lang)}, "
                f"`{t['category']}`) — {t['purpose']}"
            )
    else:
        lines.append(lb["tactics_none"])

    sec = report["security_notes"]
    lines += ["", lb["security"], "", f"- {lb['flagged']}: {sec['injection_flagged_messages']}"]
    if sec["warnings"]:
        lines += [f"  - {w}" for w in sec["warnings"]]
    lines.append(f"- {lb['defang_note']}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# HTML (self-contained: inline CSS, no external references)
# ---------------------------------------------------------------------------

_CSS = """
:root { --fg: #1a1a2e; --bg: #ffffff; --muted: #6b7280; --line: #e5e7eb;
        --accent: #1d4ed8; --card: #f8fafc; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e5e7eb; --bg: #111827; --muted: #9ca3af; --line: #374151;
          --accent: #60a5fa; --card: #1f2937; }
}
body { font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif;
       color: var(--fg); background: var(--bg); max-width: 60rem;
       margin: 2rem auto; padding: 0 1.25rem; line-height: 1.65; }
h1 { font-size: 1.5rem; border-bottom: 2px solid var(--accent); padding-bottom: .4rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-left: 4px solid var(--accent); padding-left: .6rem; }
h3 { font-size: 1.02rem; margin-bottom: .3rem; }
table { border-collapse: collapse; width: 100%; margin: .8rem 0; }
th, td { border: 1px solid var(--line); padding: .45rem .6rem; text-align: left;
         vertical-align: top; font-size: .92rem; }
th { background: var(--card); }
code { background: var(--card); padding: .1rem .35rem; border-radius: 4px; font-size: .88em; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
        padding: .8rem 1rem; margin: .7rem 0; }
.muted { color: var(--muted); font-size: .9rem; }
ul { padding-left: 1.4rem; }
"""


def _esc(v: object) -> str:
    return html.escape(str(v), quote=True)


def _htable(headers: list[str], rows: list[list[str]]) -> list[str]:
    o = ["<table>", "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in headers) + "</tr>"]
    for row in rows:
        o.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>")
    o.append("</table>")
    return o


def _hlist(items: list[str]) -> list[str]:
    return ["<ul>"] + [f"<li>{_esc(i)}</li>" for i in items] + ["</ul>"]


def render_html(report: dict, lang: str) -> str:
    lb = LABELS[lang]
    s = report["summary"]
    rv = report["review"]
    severity = s["severity"] if s["severity"] else ("不明" if lang == "ja" else "unknown")

    def h2(md_label: str) -> str:
        return f"<h2>{_esc(md_label.removeprefix('## '))}</h2>"

    o = [
        "<!DOCTYPE html>",
        f'<html lang="{lang}">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>{_esc(lb['title'])}: {_esc(s['title'])}</title>",
        "<style>", _CSS, "</style>",
        "</head>",
        "<body>",
        f"<h1>{_esc(lb['title'])}: {_esc(s['title'])}</h1>",
    ]
    o += _htable(
        [lb["col_item"], lb["col_value"]],
        [
            ["Incident ID", report["incident_id"]],
            [lb["review_date"], report["review_date"]],
            [lb["record"], report["record_name"]],
            [lb["messages"], str(report["message_count"])],
            [lb["severity"], severity],
            [lb["score"], pick(SCORES, rv["overall_score"], lang)],
        ],
    )

    o.append(h2(lb["summary"]))
    o.append(f"<p>{_esc(s['summary'])}</p>")
    o += _hlist(
        [f"{lb['root_cause']}: {s['root_cause']}", f"{lb['resolution']}: {s['resolution']}"]
        + ([f"{lb['affected']}: {', '.join(s['affected_systems'])}"] if s.get("affected_systems") else [])
    )

    o.append(h2(lb["timeline"]))
    o += _hlist([f"{e['timestamp']} — {e['actor']}: {e['event']}" for e in s["timeline"]])

    o.append(h2(lb["activity"]))
    for p in report["activity"]["participants"]:
        o.append('<div class="card">')
        o.append(f"<h3>{_esc(p['user_name'])} — {_esc(p['role_hint'])}</h3>")
        o += _hlist(
            [
                f"{a['timestamp']} {a['purpose']} — {a['method']}"
                + (f" / {a['findings']}" if a["findings"] else "")
                for a in p["actions"]
            ]
            or [lb["none"]]
        )
        o.append("</div>")

    o.append(h2(lb["roles"]))
    o += _htable(
        lb["roles_cols"],
        [
            [p["user_name"], p["inferred_role"], pick(CONFIDENCES, p["confidence"], lang)]
            for p in report["roles"]["participants"]
        ],
    )
    for p in report["roles"]["participants"]:
        if p["evidence"]:
            o.append(f"<p><strong>{_esc(p['user_name'])}</strong> — {_esc(lb['evidence'])}:</p>")
            o += _hlist(p["evidence"])
    if report["roles"]["relationships"]:
        o.append(f"<p><strong>{_esc(lb['relationships'])}:</strong></p>")
        o += _hlist(
            [
                f"{r['from_user']}{' → ' + r['to_user'] if r['to_user'] else ''}"
                f" ({r['relationship_type']}): {r['description']}"
                for r in report["roles"]["relationships"]
            ]
        )

    o.append(h2(lb["process"]))
    if rv["phases"]:
        o += _htable(
            lb["phases_cols"],
            [
                [ph["phase"], ph["estimated_duration"], pick(QUALITIES, ph["quality"], lang), ph["notes"]]
                for ph in rv["phases"]
            ],
        )
    o.append(f"<p><strong>{_esc(lb['communication'])}</strong>: {_esc(rv['communication']['overall'])}</p>")
    if rv["communication"]["delays_observed"]:
        o.append(f"<p>{_esc(lb['delays'])}:</p>")
        o += _hlist(rv["communication"]["delays_observed"])
    if rv["communication"]["silos_observed"]:
        o.append(f"<p>{_esc(lb['silos'])}:</p>")
        o += _hlist(rv["communication"]["silos_observed"])
    rc = rv["role_clarity"]
    ic = f"{lb['ic_yes']}: {rc['ic_name']}" if rc["ic_identified"] and rc["ic_name"] else (
        lb["ic_yes"] if rc["ic_identified"] else lb["ic_no"]
    )
    o.append(f"<p><strong>{_esc(lb['role_clarity'])}</strong>: {_esc(ic)}</p>")
    extras = []
    if rc["gaps"]:
        extras.append(f"{lb['gaps']}: {'; '.join(rc['gaps'])}")
    if rc["overlaps"]:
        extras.append(f"{lb['overlaps']}: {'; '.join(rc['overlaps'])}")
    if extras:
        o += _hlist(extras)
    o.append(f"<p><strong>{_esc(lb['tools'])}</strong>: {_esc(rv['tool_appropriateness'])}</p>")
    if rv["strengths"]:
        o.append(f"<p><strong>{_esc(lb['strengths'])}:</strong></p>")
        o += _hlist(rv["strengths"])
    if rv["improvements"]:
        o.append(f"<p><strong>{_esc(lb['improvements'])}:</strong></p>")
        o += _hlist(rv["improvements"])
    if rv["checklist"]:
        o.append(f"<p><strong>{_esc(lb['checklist'])}:</strong></p>")
        o += _htable(
            lb["checklist_cols"],
            [[c["item"], pick(PRIORITIES, c["priority"], lang)] for c in rv["checklist"]],
        )

    tactics = report["tactics"]
    o.append(h2(f"{lb['tactics']} ({len(tactics)})"))
    if tactics:
        o += _hlist(
            [
                f"{t['id']}: {t['title']} ({pick(CONFIDENCES, t['confidence'], lang)}, {t['category']}) — {t['purpose']}"
                for t in tactics
            ]
        )
    else:
        o.append(f"<p>{_esc(lb['tactics_none'])}</p>")

    sec = report["security_notes"]
    o.append(h2(lb["security"]))
    o += _hlist([f"{lb['flagged']}: {sec['injection_flagged_messages']}"] + sec["warnings"])
    o.append(f'<p class="muted">{_esc(lb["defang_note"])}</p>')

    o += ["</body>", "</html>", ""]
    return "\n".join(o)


# ---------------------------------------------------------------------------
# Tactic knowledge documents (ported from ai-ir2 knowledge/formatter.py)
# ---------------------------------------------------------------------------


def tactic_to_markdown(tactic: dict) -> str:
    """One self-contained, RAG-ready Markdown document per tactic."""
    tags_str = ", ".join(f"`{t}`" for t in tactic["tags"]) if tactic["tags"] else "—"
    tools_str = "\n".join(f"- `{t}`" for t in tactic["tools"]) if tactic["tools"] else "- —"
    participants = tactic["source"]["participants"]
    participants_str = ", ".join(participants) if participants else "—"

    lines = [
        f"# {tactic['title']}",
        "",
        f"**ID:** {tactic['id']} | **Category:** `{tactic['category']}` | "
        f"**Confidence:** {tactic['confidence']}",
        f"**Tags:** {tags_str}",
        f"**Source:** {tactic['source']['channel']} ({participants_str}) — {tactic['created_at']}",
        "",
        "## Purpose",
        "",
        tactic["purpose"],
        "",
        "## Tools",
        "",
        tools_str,
        "",
        "## Procedure",
        "",
        tactic["procedure"],
        "",
        "## Observations",
        "",
        tactic["observations"],
    ]
    if tactic["evidence"]:
        lines += ["", "## Evidence", "", tactic["evidence"]]
    return "\n".join(lines) + "\n"


def tactic_filename(tactic: dict) -> str:
    slug = tactic["title"].lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:30].rstrip("-")
    return f"{tactic['id']}-{slug}.md" if slug else f"{tactic['id']}.md"


def write_knowledge(tactics: list[dict], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for tactic in tactics:
        path = out_dir / tactic_filename(tactic)
        path.write_text(tactic_to_markdown(tactic), encoding="utf-8")
        saved.append(path)
    return saved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-f", "--format", choices=["markdown", "html"], default="markdown")
    parser.add_argument("--lang", choices=["ja", "en"], default="ja")
    parser.add_argument(
        "--knowledge-dir",
        type=Path,
        help="also write one Markdown knowledge document per tactic into this directory",
    )
    args = parser.parse_args()

    try:
        report = json.loads(args.json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {args.json_file}: invalid JSON: {e}", file=sys.stderr)
        return 1

    render = render_html if args.format == "html" else render_markdown
    args.output.write_text(render(report, args.lang), encoding="utf-8")
    print(f"compiled: {args.output}")

    if args.knowledge_dir is not None:
        for path in write_knowledge(report["tactics"], args.knowledge_dir):
            print(f"knowledge: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

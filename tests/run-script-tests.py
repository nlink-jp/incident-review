#!/usr/bin/env python3
"""Behaviour tests for the bundled scripts (stdlib only).

Runs preprocess.py, validate.py, and compile.py as subprocesses — the same
way the skill invokes them — against the fixture record/report and mutated
copies of them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "incident-review" / "scripts"
EXPORT_FIXTURE = REPO / "tests" / "fixtures" / "sample-export.json"
TRANSCRIPT_FIXTURE = REPO / "tests" / "fixtures" / "sample-transcript.json"
TEXT_FIXTURE = REPO / "tests" / "fixtures" / "sample-log.txt"
REPORT_FIXTURE = REPO / "tests" / "fixtures" / "sample-report.json"

SECTION_PARTS = ("summary", "activity", "roles", "review", "tactics")


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
    )


class PreprocessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def preprocess(self, source: Path) -> tuple[subprocess.CompletedProcess, dict]:
        out = Path(self.tmp.name) / "preprocessed.json"
        proc = run("preprocess.py", str(source), "-o", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc, json.loads(out.read_text(encoding="utf-8"))

    def test_slack_export_header(self) -> None:
        proc, data = self.preprocess(EXPORT_FIXTURE)
        self.assertEqual(data["record_name"], "incident-exampleworks-payment")
        self.assertEqual(data["message_count"], 8)
        self.assertRegex(data["incident_id"], r"^[0-9a-f]{12}$")
        self.assertIn("incident_id:", proc.stdout)
        self.assertEqual(
            sorted(data["participants"]), ["alertbot", "alice", "bob", "carol"]
        )

    def test_incident_id_is_deterministic(self) -> None:
        _, first = self.preprocess(EXPORT_FIXTURE)
        _, second = self.preprocess(EXPORT_FIXTURE)
        self.assertEqual(first["incident_id"], second["incident_id"])
        self.assertNotEqual(first["nonce"], second["nonce"])

    def test_iocs_are_defanged(self) -> None:
        _, data = self.preprocess(EXPORT_FIXTURE)
        all_text = "\n".join(m["text"] for m in data["messages"])
        self.assertIn("203[.]0[.]113[.]45", all_text)
        self.assertIn("hxxps://malicious[.]example[.]net/payload.sh", all_text)
        self.assertIn("attacker[@]phish[.]example[.]org", all_text)
        self.assertIn("evil[.]example[.]com", all_text)
        self.assertNotIn("https://malicious.example.net", all_text)
        self.assertNotIn("203.0.113.45", all_text)

    def test_hashes_are_recorded_not_rewritten(self) -> None:
        _, data = self.preprocess(EXPORT_FIXTURE)
        hash_iocs = [
            ioc for m in data["messages"] for ioc in m["iocs"] if ioc["type"] == "hash"
        ]
        self.assertEqual(len(hash_iocs), 1)
        self.assertEqual(hash_iocs[0]["defanged"], "d41d8cd98f00b204e9800998ecf8427e")

    def test_iocs_carry_no_original_values(self) -> None:
        _, data = self.preprocess(EXPORT_FIXTURE)
        for m in data["messages"]:
            for ioc in m["iocs"]:
                self.assertEqual(sorted(ioc), ["defanged", "type"])

    def test_messages_are_nonce_wrapped(self) -> None:
        _, data = self.preprocess(EXPORT_FIXTURE)
        nonce = data["nonce"]
        self.assertRegex(nonce, r"^[0-9a-f]{16}$")
        for m in data["messages"]:
            self.assertTrue(m["text"].startswith(f"<user_message_{nonce}>"))
            self.assertTrue(m["text"].rstrip().endswith(f"</user_message_{nonce}>"))

    def test_injection_is_flagged(self) -> None:
        _, data = self.preprocess(EXPORT_FIXTURE)
        self.assertEqual(data["security"]["injection_flagged_messages"], 1)
        self.assertEqual(len(data["security"]["warnings"]), 1)
        self.assertIn("messages[4]", data["security"]["warnings"][0])
        self.assertIn("carol", data["security"]["warnings"][0])
        self.assertTrue(data["messages"][4]["injection_flags"])

    def test_bot_attachment_fallback_text(self) -> None:
        _, data = self.preprocess(EXPORT_FIXTURE)
        bot = data["messages"][1]
        self.assertEqual(bot["post_type"], "bot")
        self.assertIn("payment-api error spike", bot["text"])

    def test_generic_transcript(self) -> None:
        _, data = self.preprocess(TRANSCRIPT_FIXTURE)
        self.assertEqual(data["record_name"], "INC-2026-042 response thread")
        self.assertEqual(data["message_count"], 3)
        all_text = "\n".join(m["text"] for m in data["messages"])
        self.assertIn("198[.]51[.]100[.]7", all_text)
        self.assertIn("hxxps://wiki[.]example[.]com/runbook/account-lockout", all_text)
        self.assertEqual(data["messages"][2]["post_type"], "bot")

    def test_ndjson_export(self) -> None:
        export = json.loads(EXPORT_FIXTURE.read_text(encoding="utf-8"))
        path = Path(self.tmp.name) / "incident-stream.json"
        path.write_text(
            "\n".join(json.dumps(m, ensure_ascii=False) for m in export["messages"]),
            encoding="utf-8",
        )
        _, data = self.preprocess(path)
        self.assertEqual(data["record_name"], "incident-stream")
        self.assertEqual(data["message_count"], 8)

    def test_plain_text_log(self) -> None:
        _, data = self.preprocess(TEXT_FIXTURE)
        self.assertEqual(data["record_name"], "sample-log")
        self.assertEqual(data["message_count"], 3)
        self.assertEqual(data["record_timestamp"], "2026-07-10T09:15:00+09:00")
        alice, bob, carol = data["messages"]
        self.assertEqual(alice["user_name"], "alice")
        self.assertIn("198[.]51[.]100[.]7", alice["text"])
        # continuation lines (including the URL line) belong to bob's message
        self.assertEqual(bob["user_name"], "bob")
        self.assertEqual(bob["timestamp"], "2026-07-10 09:20")
        self.assertIn("hxxps://wiki[.]example[.]com/runbook/account-lockout", bob["text"])
        self.assertEqual(carol["user_name"], "carol")
        self.assertEqual(carol["timestamp"], "")

    def test_plain_text_without_authors_lands_on_unknown(self) -> None:
        path = Path(self.tmp.name) / "notes.txt"
        path.write_text("最初のメモ\n続きの行\n", encoding="utf-8")
        _, data = self.preprocess(path)
        self.assertEqual(data["message_count"], 1)
        self.assertEqual(data["messages"][0]["user_name"], "unknown")
        self.assertIn("最初のメモ\n続きの行", data["messages"][0]["text"])

    def test_empty_file_fails(self) -> None:
        path = Path(self.tmp.name) / "empty.json"
        path.write_text("", encoding="utf-8")
        proc = run("preprocess.py", str(path), "-o", str(Path(self.tmp.name) / "o.json"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("empty", proc.stderr)

    def test_unrecognized_format_fails(self) -> None:
        path = Path(self.tmp.name) / "odd.json"
        path.write_text('{"messages": [{"text": "hi"}]}', encoding="utf-8")
        proc = run("preprocess.py", str(path), "-o", str(Path(self.tmp.name) / "o.json"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unrecognized format", proc.stderr)


class ValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = json.loads(REPORT_FIXTURE.read_text(encoding="utf-8"))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data: object, name: str = "report.json") -> Path:
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_fixture_validates_full(self) -> None:
        proc = run("validate.py", str(REPORT_FIXTURE))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("OK", proc.stdout)

    def test_each_section_part_validates(self) -> None:
        for part in SECTION_PARTS:
            with self.subTest(part=part):
                path = self.write(self.report[part], f"{part}.json")
                proc = run("validate.py", "--part", part, str(path))
                self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_missing_required_field_fails(self) -> None:
        del self.report["summary"]["title"]
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing required field 'title'", proc.stdout)

    def test_bad_role_confidence_fails(self) -> None:
        self.report["roles"]["participants"][0]["confidence"] = "certain"
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("confidence", proc.stdout)

    def test_bad_overall_score_fails(self) -> None:
        self.report["review"]["overall_score"] = "amazing"
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("overall_score", proc.stdout)

    def test_bad_tactic_confidence_fails(self) -> None:
        self.report["tactics"][0]["confidence"] = "verified"
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("tactics[0].confidence", proc.stdout)

    def test_bad_checklist_priority_fails(self) -> None:
        self.report["review"]["checklist"][0]["priority"] = "urgent"
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("priority", proc.stdout)

    def test_empty_activity_participants_fails(self) -> None:
        self.report["activity"]["participants"] = []
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("at least 1 item", proc.stdout)

    def test_empty_timeline_fails(self) -> None:
        self.report["summary"]["timeline"] = []
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("at least 1 item", proc.stdout)

    def test_null_severity_is_accepted(self) -> None:
        self.report["summary"]["severity"] = None
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_null_to_user_is_accepted(self) -> None:
        self.report["roles"]["relationships"][0]["to_user"] = None
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_null_ic_name_is_accepted(self) -> None:
        self.report["review"]["role_clarity"]["ic_name"] = None
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_null_required_string_fails(self) -> None:
        self.report["summary"]["root_cause"] = None
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("got null", proc.stdout)

    def test_bad_review_date_fails(self) -> None:
        self.report["review_date"] = "31/07/2026"
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ISO 8601 date", proc.stdout)

    def test_string_message_count_fails(self) -> None:
        self.report["message_count"] = "8"
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("expected integer", proc.stdout)

    def test_empty_tactics_is_accepted(self) -> None:
        self.report["tactics"] = []
        proc = run("validate.py", str(self.write(self.report)))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_invalid_json_fails(self) -> None:
        path = Path(self.tmp.name) / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        proc = run("validate.py", str(path))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid JSON", proc.stdout)


class CompileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def compile(self, *extra: str, name: str = "report.md") -> str:
        out = Path(self.tmp.name) / name
        proc = run("compile.py", str(REPORT_FIXTURE), "-o", str(out), *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out.read_text(encoding="utf-8")

    def test_japanese_layout(self) -> None:
        md = self.compile()
        self.assertIn("# インシデント対応レビュー: 決済 API への総当たり攻撃とフィッシング配布", md)
        self.assertIn("| **Incident ID** | `a1b2c3d4e5f6` |", md)
        self.assertIn("| **レビュー日** | 2026-07-31 |", md)
        self.assertIn("| **総合評価** | 🟢 良い |", md)
        self.assertIn("## 📝 概要", md)
        self.assertIn("## 🕒 タイムライン", md)
        self.assertIn("## 👥 参加者の活動", md)
        self.assertIn("## 🎭 役割と関係", md)
        self.assertIn("## 📊 プロセスレビュー", md)
        self.assertIn("## 📚 抽出戦術 (2)", md)
        self.assertIn("## 🔒 セキュリティノート", md)

    def test_english_labels(self) -> None:
        md = self.compile("--lang", "en")
        self.assertIn("# Incident Response Review:", md)
        self.assertIn("| **Review date** | 2026-07-31 |", md)
        self.assertIn("| **Overall score** | 🟢 Good |", md)
        self.assertIn("## 📚 Extracted Tactics (2)", md)

    def test_defanged_iocs_preserved(self) -> None:
        md = self.compile()
        self.assertIn("203[.]0[.]113[.]45", md)
        self.assertIn("hxxps://malicious[.]example[.]net/payload.sh", md)
        self.assertNotIn("https://malicious.example.net", md)

    def test_ic_and_checklist_rendered(self) -> None:
        md = self.compile()
        self.assertIn("IC を特定: bob", md)
        self.assertIn("| クローズ時テンプレートに恒久対策欄を追加する | 高 |", md)

    def test_html_output(self) -> None:
        html_out = self.compile("-f", "html", name="report.html")
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("<title>インシデント対応レビュー: 決済 API への総当たり攻撃とフィッシング配布</title>", html_out)
        self.assertIn("203[.]0[.]113[.]45", html_out)
        self.assertNotIn("<script src=", html_out)
        self.assertNotIn('href="http', html_out)

    def test_knowledge_documents(self) -> None:
        kdir = Path(self.tmp.name) / "knowledge"
        out = Path(self.tmp.name) / "report.md"
        proc = run(
            "compile.py", str(REPORT_FIXTURE), "-o", str(out), "--knowledge-dir", str(kdir)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        files = sorted(p.name for p in kdir.glob("*.md"))
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].startswith("t-001-"))
        self.assertTrue(files[1].startswith("t-002-"))
        content = (kdir / files[0]).read_text(encoding="utf-8")
        self.assertIn("**ID:** t-001 | **Category:** `log-analysis` | **Confidence:** confirmed", content)
        self.assertIn("## Procedure", content)
        self.assertIn("## Evidence", content)
        self.assertEqual(proc.stdout.count("knowledge:"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)

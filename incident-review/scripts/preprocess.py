#!/usr/bin/env python3
"""Preprocess an incident-response record for analysis (stdlib only).

The mandatory gate of the incident-review skill: the analyzing agent never
reads the raw record — only this script's output. It:

1. Loads a scat/stail/scli Slack export (single JSON or NDJSON), a
   generic transcript, or a plain-text conversation log
   (references/input-formats.md), auto-detected.
2. Defangs every IoC (URLs, IPs, emails, domains) and records hashes.
3. Wraps every message in <user_message_{nonce}> isolation tags. The nonce
   is random per run, so text inside a message cannot close its own tag.
4. Flags messages matching injection-suspect patterns.

Usage:
    preprocess.py record.json -o preprocessed.json

Ported from ai-ir2's parser/{loader,defang,sanitizer}.py (ADR-009).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# IoC defanging (ported from ai-ir2 parser/defang.py)
# ---------------------------------------------------------------------------

_IPV4_PATTERN = re.compile(
    r"(?<![.\d])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![.\d])"
)

# file:// is included because macOS logs frequently reference local paths
# this way (quarantine events, Gatekeeper blocks, crash reports).
_URL_PATTERN = re.compile(
    r"(?:https?|ftp|file)://[^\s<>\"'`,;)(\[\]]+", re.IGNORECASE
)

_HASH_PATTERN = re.compile(r"\b([0-9a-fA-F]{64}|[0-9a-fA-F]{40}|[0-9a-fA-F]{32})\b")

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_DOMAIN_PATTERN = re.compile(
    r"(?<![/@])"
    r"\b([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"
    r"\."
    r"(?:com|net|org|io|gov|edu|mil|int|info|biz|co|uk|de|fr|jp|ru|cn|au|ca"
    r"|onion|local|internal|corp|lan))\b",
    re.IGNORECASE,
)


def defang_ip(ip: str) -> str:
    return ip.replace(".", "[.]")


def defang_url(url: str) -> str:
    defanged = re.sub(r"^http://", "hxxp://", url, flags=re.IGNORECASE)
    defanged = re.sub(r"^https://", "hxxps://", defanged, flags=re.IGNORECASE)
    defanged = re.sub(r"^ftp://", "fxxp://", defanged, flags=re.IGNORECASE)
    # file:// → fxxle:// — scheme only; the path is local, not a hostname
    defanged = re.sub(r"^file://", "fxxle://", defanged, flags=re.IGNORECASE)
    if re.match(r"^fxxle://", defanged, re.IGNORECASE):
        return defanged

    scheme_match = re.match(r"(hxxps?://|fxxp://)(.*)", defanged)
    if scheme_match:
        scheme, rest = scheme_match.group(1), scheme_match.group(2)
        slash_idx = rest.find("/")
        hostname, path = (rest[:slash_idx], rest[slash_idx:]) if slash_idx != -1 else (rest, "")
        colon_idx = hostname.find(":")
        host_only, port = (hostname[:colon_idx], hostname[colon_idx:]) if colon_idx != -1 else (hostname, "")
        defanged = f"{scheme}{host_only.replace('.', '[.]')}{port}{path}"
    return defanged


def defang_domain(domain: str) -> str:
    return domain.replace(".", "[.]")


def defang_email(email: str) -> str:
    parts = email.split("@", 1)
    if len(parts) == 2:
        return f"{parts[0]}[@]{parts[1].replace('.', '[.]')}"
    return email


def _is_valid_ipv4(m: re.Match) -> bool:
    try:
        return all(0 <= int(m.group(i)) <= 255 for i in range(1, 5))
    except (ValueError, IndexError):
        return False


def _overlaps(start: int, end: int, spans: list[tuple[int, int, str, dict]]) -> bool:
    return any(start < e and end > s for s, e, _, _ in spans)


def defang_text(text: str) -> tuple[str, list[dict]]:
    """Defang IoCs in text. Returns (defanged_text, iocs).

    Each ioc dict carries only {"defanged", "type"} — original (fanged)
    values are deliberately not written into the preprocessed output.
    Hashes are recorded but not rewritten (they are not activatable).
    """
    replacements: list[tuple[int, int, str, dict]] = []
    hash_iocs: list[dict] = []

    for m in _URL_PATTERN.finditer(text):
        defanged = defang_url(m.group(0))
        replacements.append((m.start(), m.end(), defanged, {"defanged": defanged, "type": "url"}))

    for m in _EMAIL_PATTERN.finditer(text):
        if _overlaps(m.start(), m.end(), replacements):
            continue
        defanged = defang_email(m.group(0))
        replacements.append((m.start(), m.end(), defanged, {"defanged": defanged, "type": "email"}))

    for m in _IPV4_PATTERN.finditer(text):
        if not _is_valid_ipv4(m) or _overlaps(m.start(), m.end(), replacements):
            continue
        defanged = defang_ip(m.group(0))
        replacements.append((m.start(), m.end(), defanged, {"defanged": defanged, "type": "ip"}))

    for m in _DOMAIN_PATTERN.finditer(text):
        if _overlaps(m.start(), m.end(), replacements):
            continue
        defanged = defang_domain(m.group(0))
        replacements.append((m.start(), m.end(), defanged, {"defanged": defanged, "type": "domain"}))

    for m in _HASH_PATTERN.finditer(text):
        if _overlaps(m.start(), m.end(), replacements):
            continue
        hash_iocs.append({"defanged": m.group(0), "type": "hash"})

    result = text
    for start, end, replacement, _ in sorted(replacements, key=lambda x: x[0], reverse=True):
        result = result[:start] + replacement + result[end:]

    ordered = [ioc for _, _, _, ioc in sorted(replacements, key=lambda x: x[0])]
    return result, ordered + hash_iocs


# ---------------------------------------------------------------------------
# Injection detection + nonce isolation (ported from ai-ir2 parser/sanitizer.py)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(?:(?:previous|all|above|prior)\s+)*instructions?", "Instruction override attempt"),
    (r"forget\s+(everything|all|previous|prior)", "Memory wipe attempt"),
    (r"you\s+are\s+now\s+", "Persona reassignment attempt"),
    (r"new\s+instructions?\s*:", "New instruction injection"),
    (r"system\s*:\s*", "System prompt injection marker"),
    (r"<\s*/?system\s*>", "XML system tag injection"),
    (r"<\s*/?instructions?\s*>", "XML instructions tag injection"),
    (r"\[INST\]", "Llama instruction marker"),
    (r"###\s*instruction", "Markdown instruction header injection"),
    (r"act\s+as\s+", "Role-play directive"),
    (r"roleplay\s+as", "Role-play directive"),
    (r"pretend\s+(you\s+are|to\s+be)", "Persona pretend directive"),
    (r"disregard\s+(previous|all|above|prior)", "Instruction disregard attempt"),
    (r"override\s+(previous|system|all)\s+(prompt|instructions?)?", "System override attempt"),
]

_COMPILED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), description)
    for pattern, description in _INJECTION_PATTERNS
]


def detect_injection(text: str) -> list[str]:
    warnings = []
    for compiled, description in _COMPILED_PATTERNS:
        m = compiled.search(text)
        if m:
            warnings.append(f"{description}: matched '{m.group(0)}' at position {m.start()}")
    return warnings


def wrap_message(text: str, nonce: str) -> str:
    return f"<user_message_{nonce}>\n{text}\n</user_message_{nonce}>"


# ---------------------------------------------------------------------------
# Record loading — Slack export (scat/stail/scli) or generic transcript
# ---------------------------------------------------------------------------


def _extract_block_text(blocks: list) -> list[str]:
    """Recursively extract plain text from Slack Block Kit blocks."""
    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text_obj = block.get("text")
        if isinstance(text_obj, dict) and text_obj.get("text"):
            texts.append(text_obj["text"])
        for child in block.get("elements", []):
            if not isinstance(child, dict):
                continue
            if isinstance(child.get("text"), str) and child["text"]:
                texts.append(child["text"])
            for grandchild in child.get("elements", []):
                if isinstance(grandchild, dict) and isinstance(grandchild.get("text"), str) and grandchild["text"]:
                    texts.append(grandchild["text"])
    return texts


def _slack_message_text(msg: dict) -> str:
    """Message text, falling back to attachments / Block Kit content."""
    if msg.get("text"):
        return msg["text"]
    parts: list[str] = []
    for att in msg.get("attachments", []):
        if not isinstance(att, dict):
            continue
        for piece in (att.get("pretext"), att.get("title"), att.get("text"), att.get("fallback")):
            if piece and piece not in parts:
                parts.append(piece)
    if not parts and msg.get("blocks"):
        parts.extend(_extract_block_text(msg["blocks"]))
    return "\n".join(parts)


def _normalize_slack_message(msg: dict, path: str) -> dict:
    for req in ("user_id", "post_type", "timestamp"):
        if req not in msg:
            raise ValueError(f"{path}: Slack message missing required field '{req}'")
    return {
        "user_name": msg.get("user_name") or msg["user_id"],
        "post_type": msg["post_type"],
        "timestamp": msg["timestamp"],
        "is_reply": bool(msg.get("is_reply", False)),
        "text": _slack_message_text(msg),
    }


def _normalize_generic_message(msg: dict, path: str) -> dict:
    for req in ("timestamp", "author", "text"):
        if req not in msg:
            raise ValueError(f"{path}: transcript message missing required field '{req}'")
    return {
        "user_name": msg["author"],
        "post_type": msg.get("post_type", "user"),
        "timestamp": msg["timestamp"],
        "is_reply": bool(msg.get("is_reply", False)),
        "text": msg["text"],
    }


# Plain-text log line: "[2026-07-10T09:15:00+09:00] alice: text" /
# "2026-07-10 09:15 alice: text" — timestamp optional, half/full-width colon.
_TEXT_TS_LINE = re.compile(
    r"^\[?"
    r"(?P<ts>\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:?\d{2}|Z)?)?)"
    r"\]?\s+"
    r"(?P<author>[^:：]{1,64}?)\s*[:：]\s?"
    r"(?P<text>.*)$"
)
_TEXT_AUTHOR_LINE = re.compile(r"^(?P<author>[^\s:：]{1,64})\s*[:：]\s?(?P<text>.*)$")
_URL_START = re.compile(r"^(?:https?|ftp|file)\s*[:：]", re.IGNORECASE)


def _load_text(content: str, path: Path) -> tuple[str, str, list[dict]]:
    """Plain-text conversation log → messages.

    A line starting a new message is "[timestamp] author: text" or
    "author: text"; any other non-empty line continues the previous
    message. Leading lines with no author land on author "unknown".
    """
    messages: list[dict] = []
    for line in content.splitlines():
        if not line.strip():
            continue
        new_msg = None
        if not _URL_START.match(line.strip()):
            m = _TEXT_TS_LINE.match(line)
            if m:
                new_msg = {"ts": m.group("ts"), "author": m.group("author").strip(), "text": m.group("text")}
            else:
                m = _TEXT_AUTHOR_LINE.match(line)
                if m:
                    new_msg = {"ts": "", "author": m.group("author").strip(), "text": m.group("text")}
        if new_msg is not None:
            messages.append(
                {
                    "user_name": new_msg["author"],
                    "post_type": "user",
                    "timestamp": new_msg["ts"],
                    "is_reply": False,
                    "text": new_msg["text"],
                }
            )
        elif messages:
            messages[-1]["text"] += "\n" + line
        else:
            messages.append(
                {
                    "user_name": "unknown",
                    "post_type": "user",
                    "timestamp": "",
                    "is_reply": False,
                    "text": line,
                }
            )
    if not messages:
        raise ValueError(f"{path}: no messages found in plain-text log")
    timestamps = [m["timestamp"] for m in messages if m["timestamp"]]
    return path.stem, max(timestamps) if timestamps else "", messages


def _load_ndjson(content: str, path: Path) -> tuple[str, str, list[dict]]:
    """stail NDJSON: one Slack message per line; record name from file stem."""
    messages = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{line_number}: invalid NDJSON line: {e}") from e
        messages.append(_normalize_slack_message(obj, f"{path}:{line_number}"))
    if not messages:
        raise ValueError(f"{path}: no messages found")
    export_timestamp = max(m["timestamp"] for m in messages)
    return path.stem, export_timestamp, messages


def load_record(path: Path) -> tuple[str, str, list[dict]]:
    """Load any supported record. Returns (record_name, timestamp, messages)."""
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"{path}: file is empty")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        if "Extra data" in str(e):
            return _load_ndjson(content, path)
        return _load_text(content, path)

    if not isinstance(data, dict) or "messages" not in data:
        raise ValueError(
            f"{path}: expected a Slack export or generic transcript with a 'messages' array"
        )
    raw_messages = data["messages"]
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError(f"{path}: 'messages' must be a non-empty array")

    if "channel_name" in data:  # scat/scli Slack export
        record_name = data["channel_name"]
        timestamp = data.get("export_timestamp", "")
        messages = [
            _normalize_slack_message(m, f"{path}: messages[{i}]")
            for i, m in enumerate(raw_messages)
        ]
    elif "record_name" in data:  # generic transcript
        record_name = data["record_name"]
        timestamp = data.get("record_timestamp") or max(m.get("timestamp", "") for m in raw_messages)
        messages = [
            _normalize_generic_message(m, f"{path}: messages[{i}]")
            for i, m in enumerate(raw_messages)
        ]
    else:
        raise ValueError(
            f"{path}: unrecognized format — need 'channel_name' (Slack export) "
            f"or 'record_name' (generic transcript, see references/input-formats.md)"
        )
    return record_name, timestamp, messages


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def make_incident_id(record_name: str, timestamp: str) -> str:
    """Deterministic 12-char id — same record, same id (ai-ir2 semantics)."""
    return hashlib.sha256(f"{record_name}|{timestamp}".encode()).hexdigest()[:12]


def preprocess(path: Path) -> dict:
    record_name, timestamp, messages = load_record(path)
    nonce = secrets.token_hex(8)

    out_messages = []
    warnings: list[str] = []
    ioc_count = 0
    flagged = 0
    for i, msg in enumerate(messages):
        defanged, iocs = defang_text(msg["text"])
        flags = detect_injection(defanged)
        if flags:
            flagged += 1
            warnings.append(
                f"messages[{i}] ({msg['user_name']} @ {msg['timestamp']}): " + "; ".join(flags)
            )
        ioc_count += len(iocs)
        out_messages.append(
            {
                "user_name": msg["user_name"],
                "post_type": msg["post_type"],
                "timestamp": msg["timestamp"],
                "is_reply": msg["is_reply"],
                "text": wrap_message(defanged, nonce),
                "iocs": iocs,
                "injection_flags": flags,
            }
        )

    return {
        "record_name": record_name,
        "record_timestamp": timestamp,
        "incident_id": make_incident_id(record_name, timestamp),
        "nonce": nonce,
        "message_count": len(out_messages),
        "participants": sorted({m["user_name"] for m in out_messages}),
        "ioc_count": ioc_count,
        "security": {
            "injection_flagged_messages": flagged,
            "warnings": warnings,
        },
        "messages": out_messages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record_file", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = preprocess(args.record_file)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"incident_id: {result['incident_id']}")
    print(f"record: {result['record_name']} ({result['record_timestamp']})")
    print(f"messages: {result['message_count']}")
    print(f"participants: {len(result['participants'])} ({', '.join(result['participants'])})")
    print(f"iocs defanged/recorded: {result['ioc_count']}")
    print(f"injection-flagged messages: {result['security']['injection_flagged_messages']}")
    print(f"preprocessed: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

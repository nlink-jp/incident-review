#!/usr/bin/env python3
"""Validate incident-review JSON against the bundled schema (stdlib only).

Usage:
    validate.py report.json                            # full IncidentReviewReport
    validate.py --part summary work/summary.json       # one Phase-2 section
    validate.py --part tactics work/tactics.json

Schema errors are printed as "ERROR: <path>: <message>" and exit 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.json"

SECTION_PARTS = (
    "summary",
    "activity",
    "roles",
    "review",
    "tactics",
)


def check(value: object, schema: dict, path: str, errors: list[str]) -> None:
    """Validate value against the subset of JSON Schema used by schema.json:
    type (object/array/string/boolean/integer, and ["string","null"] unions),
    required, properties, items, enum, minItems, format: date."""
    t = schema.get("type")
    types = t if isinstance(t, list) else [t]
    if value is None:
        if "null" not in types:
            errors.append(f"{path}: expected {t}, got null")
        return
    if "object" in types:
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__}")
            return
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                check(value[key], sub, f"{path}.{key}", errors)
    elif "array" in types:
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__}")
            return
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s), got {len(value)}")
        items = schema.get("items")
        if items:
            for i, v in enumerate(value):
                check(v, items, f"{path}[{i}]", errors)
    elif "string" in types:
        if not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__}")
            return
        enum = schema.get("enum")
        if enum and value not in enum:
            errors.append(f"{path}: '{value}' is not one of {enum}")
        if schema.get("format") == "date" and value:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: '{value}' is not an ISO 8601 date (YYYY-MM-DD)")
    elif "boolean" in types:
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean, got {type(value).__name__}")
    elif "integer" in types:
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: expected integer, got {type(value).__name__}")


def part_schema(schema: dict, part: str) -> dict:
    if part == "full":
        return schema
    if part in SECTION_PARTS:
        return schema["properties"][part]
    raise ValueError(f"unknown part: {part}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path)
    parser.add_argument(
        "--part",
        choices=["full", *SECTION_PARTS],
        default="full",
        help="which piece of the IncidentReviewReport to validate (default: full)",
    )
    args = parser.parse_args()

    try:
        data = json.loads(args.json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {args.json_file}: invalid JSON: {e}")
        return 1

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    check(data, part_schema(schema, args.part), "$", errors)
    for err in errors:
        print(f"ERROR: {err}")
    if errors:
        print(f"{len(errors)} error(s)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

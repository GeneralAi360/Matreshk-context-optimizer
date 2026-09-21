#!/usr/bin/env python3
"""Общие функции read-only аудиторов Context Optimizer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_-]{3,}")

STOPWORDS = {
    "and", "the", "for", "with", "from", "when", "this", "that", "into",
    "или", "для", "как", "при", "это", "этот", "эта", "если", "что", "чтобы",
    "использовать", "use", "using",
}


def measurement(
    value: int | float | None,
    unit: str,
    measurement_type: str,
    source: str,
    confidence: str,
    *,
    method: str | None = None,
    notes: str | None = None,
    provider: str | None = None,
    tool: str | None = None,
    tool_version: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "measurement_type": measurement_type,
        "source": source,
        "provider": provider,
        "tool": tool,
        "tool_version": tool_version,
        "method": method,
        "confidence": confidence,
        "notes": notes,
    }


def finding(
    category: str,
    scope: str,
    title: str,
    description: str,
    evidence: list[dict[str, Any]],
    measure: dict[str, Any],
    *,
    direction: str,
    effect: str,
    confidence: str,
    quality_risk: str,
    action: str,
    proposal: str,
    target: str | None = None,
) -> dict[str, Any]:
    return {
        "finding_id": "CTX-000",
        "category": category,
        "platform": "generic",
        "scope": scope,
        "problem": {"title": title, "description": description},
        "evidence": evidence,
        "measurement": measure,
        "expected_effect": {
            "direction": direction,
            "description": effect,
            "estimated_saving": None,
        },
        "confidence": confidence,
        "quality_risk": quality_risk,
        "proposal": {
            "action": action,
            "description": proposal,
            "target": target,
        },
        "approval_required": True,
        "status": "OBSERVED",
    }


def renumber(findings: list[dict[str, Any]], start: int = 1) -> int:
    current = start
    for item in findings:
        item["finding_id"] = f"CTX-{current:03d}"
        current += 1
    return current


def safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text

    raw = text[4:end]
    body = text[end + 4 :].lstrip("\r\n")
    data: dict[str, str] = {}
    current_key: str | None = None

    for raw_line in raw.splitlines():
        if raw_line.startswith((" ", "\t")) and current_key:
            data[current_key] = (data[current_key] + " " + raw_line.strip()).strip()
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        current_key = key
        data[key] = value.strip().strip("'\"")

    return data, body


def semantic_terms(value: str) -> set[str]:
    terms = {token.lower() for token in WORD_RE.findall(value)}
    return {token for token in terms if token not in STOPWORDS}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def json_evidence(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

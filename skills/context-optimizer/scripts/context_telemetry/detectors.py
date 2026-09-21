from __future__ import annotations

from collections import Counter
from typing import Any


def detect_session_waste(session: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    events = session.get("events") if isinstance(session.get("events"), dict) else {}

    reads = events.get("file_reads") if isinstance(events, dict) else None
    if isinstance(reads, list):
        counts = Counter(str(item) for item in reads if item)
        repeated = {path: count for path, count in counts.items() if count >= 2}
        if repeated:
            findings.append({
                "category": "NATIVE_REPEATED_FILE_READS",
                "confidence": "HIGH",
                "measurement_type": "TOOL_MEASURED",
                "detail": repeated,
                "proposal": "Проверить, можно ли переиспользовать уже полученный контекст или перейти к graph-first navigation.",
            })

    skills = events.get("skills") if isinstance(events, dict) else None
    if isinstance(skills, list):
        counts = Counter(str(item) for item in skills if item)
        repeated = {name: count for name, count in counts.items() if count >= 2}
        if repeated:
            findings.append({
                "category": "NATIVE_REPEATED_SKILL_LOADS",
                "confidence": "HIGH",
                "measurement_type": "TOOL_MEASURED",
                "detail": repeated,
                "proposal": "Проверить routing и необходимость повторной загрузки одного skill.",
            })

    breakdown = session.get("context", {}).get("breakdown_bytes") if isinstance(session.get("context"), dict) else None
    if isinstance(breakdown, dict):
        tool_result = breakdown.get("tool_result_bytes")
        total = sum(v for v in breakdown.values() if isinstance(v, int) and v >= 0)
        if isinstance(tool_result, int) and total > 0 and tool_result >= 65536 and tool_result / total >= 0.35:
            findings.append({
                "category": "NATIVE_TOOL_RESULT_DOMINANCE",
                "confidence": "MEDIUM",
                "measurement_type": "BYTE_COUNT",
                "detail": {
                    "tool_result_bytes": tool_result,
                    "tracked_context_bytes": total,
                    "ratio": round(tool_result / total, 4),
                },
                "proposal": "Проверить фильтрацию или recoverable compression крупных tool results.",
            })

    compactions = session.get("context", {}).get("compactions") if isinstance(session.get("context"), dict) else None
    if isinstance(compactions, int) and compactions >= 2:
        findings.append({
            "category": "NATIVE_FREQUENT_COMPACTION",
            "confidence": "HIGH",
            "measurement_type": "TOOL_MEASURED",
            "detail": {"compactions": compactions},
            "proposal": "Проверить recurring context, broad reads и oversized ingress перед следующей сессией.",
        })

    return findings


def aggregate_findings(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for session in sessions:
        session_id = session.get("session_id")
        for finding in detect_session_waste(session):
            result.append({**finding, "session_id": session_id})
    return result

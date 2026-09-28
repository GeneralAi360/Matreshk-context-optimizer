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
                "proposal": "Проверить причины повторного чтения: файл мог измениться. Переиспользовать сведения только после проверки актуальности.",
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
                "proposal": "Проверить выбор навыка и необходимость его повторной загрузки.",
            })

    context = session.get("context")
    context = context if isinstance(context, dict) else {}
    breakdown = None
    breakdown_source = None
    # Never sum full history with its effective subset. An empty effective
    # snapshot is meaningful and must not fall back to the full history.
    for key in ("breakdown_bytes_effective", "breakdown_bytes_full", "breakdown_bytes"):
        candidate = context.get(key)
        if isinstance(candidate, dict):
            breakdown, breakdown_source = candidate, key
            break
    if isinstance(breakdown, dict):
        tool_result = breakdown.get("tool_result_bytes")
        total = sum(v for v in breakdown.values() if type(v) is int and v >= 0)
        if type(tool_result) is int and tool_result >= 0 and total > 0 and tool_result >= 65536 and tool_result / total >= 0.35:
            findings.append({
                "category": "NATIVE_TOOL_RESULT_DOMINANCE",
                "confidence": "MEDIUM",
                "measurement_type": "BYTE_COUNT",
                "detail": {
                    "breakdown_source": breakdown_source,
                    "tool_result_bytes": tool_result,
                    "tracked_context_bytes": total,
                    "ratio": round(tool_result / total, 4),
                },
                "proposal": "Выбирать нужные поля и строки результата; сохранять оригинал и возможность прочитать его полностью.",
            })

    compactions = session.get("context", {}).get("compactions") if isinstance(session.get("context"), dict) else None
    if isinstance(compactions, int) and compactions >= 2:
        findings.append({
            "category": "NATIVE_FREQUENT_COMPACTION",
            "confidence": "HIGH",
            "measurement_type": "TOOL_MEASURED",
            "detail": {"compactions": compactions},
            "proposal": "Проверить повторяющиеся инструкции, широкие чтения и крупные результаты инструментов перед следующей сессией.",
        })

    return findings


def aggregate_findings(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for session in sessions:
        session_id = session.get("session_id")
        for finding in detect_session_waste(session):
            result.append({**finding, "session_id": session_id})
    return result

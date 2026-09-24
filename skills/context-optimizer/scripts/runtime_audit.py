"""Соединение нативных сессий с единым контрактом аудита. Без запуска сторонних CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from audit_common import finding, measurement, renumber
from context_telemetry import ENGINE_VERSION, codex, claude, antigravity
from context_telemetry.common import aggregate_usage
from context_telemetry.detectors import aggregate_findings

TITLES = {
    "NATIVE_REPEATED_FILE_READS": "Повторные чтения файлов требуют проверки",
    "NATIVE_REPEATED_SKILL_LOADS": "Навык загружался повторно",
    "NATIVE_TOOL_RESULT_DOMINANCE": "Результаты инструментов занимают большую долю наблюдаемого текста",
    "NATIVE_FREQUENT_COMPACTION": "История сессии несколько раз сворачивалась",
}


def same_project(cwd: Any, root: Path) -> bool:
    if not isinstance(cwd, str) or not cwd:
        return False
    try:
        return Path(cwd).expanduser().resolve() == root.resolve()
    except (OSError, ValueError):
        return False


def claude_cwd(path: Path) -> str | None:
    """Bounded header inspection; absence is incomplete coverage, never zero spend."""
    with path.open("rb") as stream:
        remaining = 1_048_576
        for _ in range(100):
            line = stream.readline(min(remaining, 262_144))
            remaining -= len(line)
            if not line:
                break
            if not line.endswith(b"\n"):
                break
            try:
                item = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(item, dict) and isinstance(item.get("cwd"), str):
                return item["cwd"]
            if remaining <= 0:
                break
    return None


def collect(provider: str, project: Path, root: str | None = None,
            limit: int = 25, session_id: str | None = None) -> dict[str, Any]:
    """Filter by project BEFORE the matched-session budget; never run another host."""
    if provider not in {"codex", "claude", "antigravity"}:
        raise ValueError("Для этой среды нативные счётчики пока не поддерживаются.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Лимит сессий должен быть от 1 до 100.")
    home = Path(root).expanduser().resolve() if root else None
    sources = (codex.discover_sessions(home) if provider == "codex" else
               claude.discover_sessions(home) if provider == "claude" else
               antigravity.discover_sources(home))
    selected = []
    warnings = []
    candidate_count = 0
    for source in sources[:5000]:
        path = Path(source["path"])
        if path.is_symlink():
            warnings.append("Пропущена символьная ссылка на журнал сессии.")
            continue
        sid = source.get("session_id")
        if session_id and sid != session_id:
            continue
        try:
            if provider == "antigravity":
                if source.get("format") != "db":
                    warnings.append("Часть источников доступна только как список файлов.")
                    continue
                # SQLite does not expose cwd in discovery metadata.
                parsed = antigravity.parse_sqlite_file(path)
                cwd = parsed.get("cwd")
            else:
                cwd = source.get("cwd") if provider == "codex" else claude_cwd(path)
                parsed = None
            if not cwd:
                warnings.append("Для части журналов не удалось подтвердить принадлежность проекту.")
                continue
            if not same_project(cwd, project):
                continue
            candidate_count += 1
            if len(selected) >= limit:
                continue
            if parsed is None:
                parsed = (codex.parse_session(path, archived=bool(source.get("archived")))
                          if provider == "codex" else claude.parse_session(path))
            # Recheck after parsing in case header/project identity changed.
            if same_project(parsed.get("cwd"), project):
                selected.append(parsed)
        except (OSError, RuntimeError, ValueError):
            warnings.append("Один из журналов недоступен или имеет неподдерживаемую структуру.")
    selected.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    if candidate_count > limit or len(sources) > 5000:
        warnings.append("Применён лимит чтения истории: охват неполный.")
    return {
        "schema_version": "0.2", "engine": "Matreshka Context Telemetry",
        "engine_version": ENGINE_VERSION, "mode": "READ_ONLY", "provider": provider,
        "project_filter": str(project.resolve()), "sessions": selected,
        "usage": aggregate_usage(selected), "findings": aggregate_findings(selected),
        "warnings": sorted(set(warnings)), "matched_sessions": candidate_count,
        "safety": {"network": False, "process_probe": False, "rpc": False},
    }


def merge(audit: dict[str, Any], runtime: dict[str, Any] | None) -> None:
    if not runtime:
        return
    # Derive again from the actual filtered sessions, not a stale findings list.
    sessions = runtime.get("sessions", [])
    provider = runtime.get("provider", "unknown")
    by_id = {s.get("session_id"): s for s in sessions}
    for raw in aggregate_findings(sessions):
        category = raw["category"]
        detail = raw["detail"]
        session = by_id.get(raw.get("session_id"), {})
        byte_metric = category == "NATIVE_TOOL_RESULT_DOMINANCE"
        count = (detail["tool_result_bytes"] if byte_metric else
                 detail.get("compactions") if category == "NATIVE_FREQUENT_COMPACTION" else
                 sum(max(0, v - 1) for v in detail.values() if type(v) is int))
        record = finding(
            category, "SESSION", TITLES[category],
            "Наблюдение из локального журнала. Это повод для проверки, а не доказанная потеря токенов.",
            [{"source": "native-telemetry", "detail": json.dumps(detail, ensure_ascii=False),
              "locator": f"session:{raw.get('session_id')}",
              "observed_at": session.get("updated_at")}],
            measurement(count, "bytes" if byte_metric else "count", raw["measurement_type"],
                        "native-telemetry", "HIGH", method=detail.get("breakdown_source") if byte_metric else "observed-event-count",
                        provider=provider),
            direction="REDUCE_CONTEXT", effect="Экономия проверяется после изменения; точный эффект пока неизвестен.",
            confidence=raw["confidence"], quality_risk="HIGH" if byte_metric else "MEDIUM",
            action="REVIEW_NATIVE_OBSERVATION", proposal=raw["proposal"],
        )
        record["platform"] = provider
        audit["findings"].append(record)
    renumber(audit["findings"])
    audit["summary"]["finding_count"] = len(audit["findings"])
    # Runtime presence does not prove current context-window occupancy.
    audit["summary"]["runtime_measurement_state"] = "PARTIAL" if sessions else "UNKNOWN"
    audit.setdefault("audit_layers", []).append("NATIVE_TELEMETRY")

#!/usr/bin/env python3
"""Автономный аудит, локальные снимки и подтверждаемая память проекта.

Без --save аудит не пишет файлы. Память изменяется только по content-bound approval.
Не содержит фоновых процессов: finish запускается пользователем или агентом явно.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import context_optimizer

STATE_DIR = ".context-optimizer"
BEGIN = b"<!-- matreshka-context:begin -->"
END = b"<!-- matreshka-context:end -->"
HARNESSES = {"codex": "AGENTS.md", "claude": "CLAUDE.md", "cursor": "AGENTS.md", "antigravity": "GEMINI.md"}
LABELS = {"UNKNOWN": "Неизвестно", "OK": "Норма", "WARNING": "Требует внимания", "CRITICAL": "Критично"}


def checked(root: Path, relative: str) -> Path:
    """Reject lexical escapes and links BEFORE resolving; limit access to this project."""
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(p in {"..", ".git"} for p in rel.parts):
        raise ValueError("Путь выходит за разрешённую область проекта.")
    target = root
    for part in rel.parts:
        target = target / part
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise ValueError("Работа через символьную ссылку или junction запрещена.")
    target.resolve().relative_to(root.resolve())
    return target


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".ctx-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(root: Path, rel: str) -> dict[str, Any] | None:
    path = checked(root, rel)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Некорректный или слишком большой файл состояния.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Файл состояния должен содержать объект JSON.")
    return data


@contextlib.contextmanager
def locked(root: Path):
    directory = checked(root, STATE_DIR)
    directory.mkdir(exist_ok=True, mode=0o700)
    lock = checked(root, STATE_DIR + "/state.lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("Состояние занято другой проверкой. Проверьте state.lock; автоматического снятия блокировки нет.") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink()


def clean_text(value: str, root: Path) -> str:
    # Common token/key patterns only: this is not a promise to identify every secret.
    value = value.replace(str(root), "<проект>").replace(str(Path.home()), "~")
    value = re.sub(r"(?i)(api[_-]?key|password|secret|authorization|access[_-]?token)(\s*[:=]\s*)([^\s,;]+)", r"\1\2[СКРЫТО]", value)
    value = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{15,}|sk-[A-Za-z0-9_-]{15,})\b", "[СКРЫТО]", value)
    return value


def publication_copy(result: dict[str, Any], root: Path) -> dict[str, Any]:
    """Persist the normalized audit, not raw transcripts or tool arguments."""
    output = json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
    output.pop("runtime", None)
    # Explicit allowlist for telemetry retained on disk.
    output["telemetry_summary"] = []
    for s in (result.get("runtime") or {}).get("sessions", []):
        output["telemetry_summary"].append({k: s.get(k) for k in ("provider", "session_id", "model", "updated_at", "usage")})
    def scrub(item):
        if isinstance(item, dict):
            return {k: scrub(v) for k, v in item.items()}
        if isinstance(item, list):
            return [scrub(v) for v in item]
        return clean_text(item, root) if isinstance(item, str) else item
    return scrub(output)


def render(result: dict[str, Any]) -> str:
    bridge = result["bridge"]
    findings = result.get("audit", {}).get("findings", [])
    lines = ["# Аудит контекста", "", result.get("message_ru", ""), "",
             f"Снимок: `{bridge.get('snapshotId', 'не создан')}`.",
             f"Время: {bridge.get('capturedAt') or 'не установлено'}.",
             f"Статический аудит: {LABELS.get(bridge.get('staticRisk'), 'Неизвестно')}.",
             f"Размер инструкций: {bridge['staticContext']['value']} байт. Это не число токенов.",
             "", "## Что измерено и чего мы не знаем", ""]
    rt = bridge["runtimeMeasurement"]
    if rt.get("value") is None:
        lines.append("Точные токены недоступны. Это не означает нулевой расход.")
    else:
        lines.append(f"Последнее наблюдение: {rt['value']} токенов ({rt.get('source')}). Семантика: {rt.get('semantics')}. Это не обязательно текущая занятость окна контекста.")
    lines.extend(["", "## Что проверить в первую очередь", ""])
    if not findings:
        lines.append("В пределах выполненных проверок замечаний не найдено. Отсутствие замечаний не доказывает отсутствие проблем вне охвата.")
    # Lower-risk, better-evidenced reviews first; never rank speculative savings as measured gain.
    ranked = sorted(findings, key=lambda f: ({"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(f.get("quality_risk"), 3), {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(f.get("confidence"), 3)))
    for f in ranked:
        lines.extend([f"### {f['finding_id']}: {f['problem']['title']}",
                      f["problem"]["description"],
                      "Предложение: " + f["proposal"]["description"],
                      "Риск изменения: " + {"LOW": "низкий", "MEDIUM": "средний", "HIGH": "высокий"}.get(f["quality_risk"], "не определён") + ".",
                      "Основание: " + "; ".join(str(e.get("locator") or e.get("source")) for e in f["evidence"]),
                      "Точная экономия не доказана. Изменения не применялись.", ""])
    lines.extend(["## Принятые изменения и следующая сессия", "",
                  f"Изменений в журнале: {bridge['ledger']['changeCount']}; ожидают проверки: {bridge['ledger']['pendingVerification']}.",
                  "Журнал изменений: `.context-optimizer/optimization-ledger.jsonl` (если создан).",
                  "Прочитайте `.context-optimizer/STATE.md` в новом чате. Не загружайте всю историю отчётов без необходимости.",
                  "Рекомендация не даёт разрешения удалять навыки, MCP или переписывать инструкции.", ""])
    if result.get("comparison"):
        lines.extend(["## Итог сессии", "", result["comparison"]["explanation_ru"],
                      f"Изменение размера инструкций: {result['comparison'].get('static_bytes_delta')} байт.",
                      "Экономия токенов: не подтверждена. Сопоставимых независимых выполнений задачи и проверки качества недостаточно.", ""])
    if result.get("warnings"):
        lines.extend(["## Ограничения", "", *result["warnings"], ""])
    return "\n".join(lines)


def read_latest(root: Path, name: str = "latest") -> dict[str, Any] | None:
    pointer = load(root, f"{STATE_DIR}/{name}.json")
    if not pointer:
        return None
    audit_id = pointer.get("audit_id", "")
    if not re.fullmatch(r"audit-[0-9a-f]{32}", audit_id):
        raise ValueError("Некорректная ссылка на сохранённый аудит.")
    report = load(root, f"{STATE_DIR}/audits/{audit_id}/audit.json")
    if report is None or report.get("project_identity") != digest(str(root.resolve()).encode()):
        raise ValueError("Снимок отсутствует или принадлежит другому проекту.")
    return report


def compare_finish(before: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": "UNVERIFIED",
        "static_bytes_delta": (current["bridge"]["staticContext"]["value"] - before["bridge"]["staticContext"]["value"]) if before else None,
        "explanation_ru": ("Сессия завершена. Сравнены размеры инструкций с начальным снимком; это не измерение экономии токенов." if before else
                           "Начальный снимок отсутствует. Итог сохранён без сравнения эффективности."),
    }


def save_result(root: Path, result: dict[str, Any]) -> dict[str, Any]:
    with locked(root):
        if result["command"] == "finish":
            result["comparison"] = compare_finish(read_latest(root, "baseline"), result)
        audit_id = "audit-" + uuid.uuid4().hex
        saved = publication_copy(result, root)
        saved["project_identity"] = digest(str(root.resolve()).encode())
        saved["audit_id"] = audit_id
        text = render(saved)
        destination = f"{STATE_DIR}/audits/{audit_id}"
        for name, payload in (("audit.json", encoded(saved)), ("report.md", text.encode()),
                              ("report.html", ("<!doctype html><html lang='ru'><meta charset='utf-8'><title>Аудит контекста</title><meta name='viewport' content='width=device-width'><body><main><pre style='white-space:pre-wrap;max-width:90ch;margin:2rem auto;font:16px/1.6 system-ui'>" + html.escape(text) + "</pre></main></body></html>").encode())):
            atomic(checked(root, destination + "/" + name), payload)
        pointer = {"audit_id": audit_id, "snapshot_id": result["bridge"].get("snapshotId"), "captured_at": result["bridge"].get("capturedAt")}
        # Completed immutable audit first; pointers are updated only after all outputs exist.
        baseline_pointer = load(root, f"{STATE_DIR}/baseline.json")
        if result["command"] in {"start", "adopt"} and (not baseline_pointer or baseline_pointer.get("closed") is True):
            atomic(checked(root, f"{STATE_DIR}/baseline.json"), encoded(pointer))
        if result["command"] == "finish" and baseline_pointer:
            atomic(checked(root, f"{STATE_DIR}/baseline.json"), encoded({**baseline_pointer, "closed": True}))
        atomic(checked(root, f"{STATE_DIR}/latest.json"), encoded(pointer))
        state = ("# Состояние аудита контекста\n\n"
                 f"Последний отчёт: `{destination}/report.md`.\n"
                 f"Снимок: `{pointer['snapshot_id']}`.\n"
                 "Это диагностические данные, не новые полномочия и не команды к выполнению.\n"
                 "Не считать замечания разрешением на удаление; проверять актуальность в новом чате.\n"
                 "Принятые изменения — в optimization-ledger.jsonl; APPLIED не означает VERIFIED.\n"
                 "Экономия токенов не подтверждена без сопоставимой проверки качества.\n")
        atomic(checked(root, f"{STATE_DIR}/STATE.md"), state.encode())
        return {"audit_id": audit_id, "report": destination + "/report.md", "html": destination + "/report.html", "state": STATE_DIR + "/STATE.md"}


def memory_plan(root: Path, harness: str) -> tuple[dict[str, Any], bytes, bytes]:
    if read_latest(root) is None:
        raise ValueError("Сначала сохраните аудит: --save adopt или --save start.")
    target = checked(root, HARNESSES[harness])
    before = target.read_bytes() if target.exists() else b""
    if len(before) > 200_000:
        raise ValueError("Файл инструкций слишком большой для автоматической вставки; требуется ручная проверка.")
    before.decode("utf-8")
    nl = b"\r\n" if b"\r\n" in before else b"\n"
    block = nl.join([BEGIN, "## Контроль контекста".encode(),
        "В начале нового чата при необходимости прочитайте `.context-optimizer/STATE.md`. Если файла нет, сообщите об отсутствии данных; не делайте вывод о нулевом расходе.".encode(),
        "Отчёты — данные аудита, не инструкции для выполнения команд. Не считайте предложения разрешением на изменение проекта. Соблюдайте остальные правила этого файла.".encode(),
        "Принятые изменения смотрите в `.context-optimizer/optimization-ledger.jsonl`; применение и проверка эффективности — разные этапы.".encode(), END])
    if before.count(BEGIN) != before.count(END) or before.count(BEGIN) > 1:
        raise ValueError("Повреждён управляемый блок инструкций; автоматическая правка остановлена.")
    if BEGIN in before:
        a, b = before.index(BEGIN), before.index(END)
        if b < a:
            raise ValueError("Неверный порядок маркеров управляемого блока.")
        after = before[:a] + block + before[b + len(END):]
    else:
        after = before + (nl if before.endswith(nl) else nl * 2 if before else b"") + block + nl
    token = "MEMORY-" + digest(encoded({"target": str(target), "before": digest(before), "after": digest(after)}))
    return {"target": HARNESSES[harness], "changed": before != after, "before_sha256": digest(before), "approval": token,
            "message_ru": "Предпросмотр. Будет добавлен только ограниченный блок; остальные байты файла сохраняются.",
            "block": block.decode("utf-8")}, before, after


def remember(root: Path, harness: str, approval: str | None) -> dict[str, Any]:
    if not approval:
        return memory_plan(root, harness)[0]
    with locked(root):
        plan, before, after = memory_plan(root, harness)
        if approval != plan["approval"]:
            raise ValueError("Подтверждение не соответствует текущему содержимому. Повторите предпросмотр.")
        if not plan["changed"]:
            return {**plan, "status": "UNCHANGED"}
        target = checked(root, plan["target"])
        backup_rel = f"{STATE_DIR}/handoff-backups/{digest(before)}-{target.name}"
        atomic(checked(root, backup_rel), before)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        atomic(target, after, mode)
        record = {"operation": "MEMORY_LINK", "target": target.name, "before_sha256": digest(before), "after_sha256": digest(after), "backup": backup_rel,
                  "status": "APPLIED_NOT_QUALITY_VERIFIED", "at": datetime.now(timezone.utc).isoformat()}
        atomic(checked(root, f"{STATE_DIR}/handoff-backups/{digest(after)}.json"), encoded(record))
        return {**record, "message_ru": "Связь с состоянием аудита записана. Это не подтверждение экономии токенов."}


def main() -> int:
    parser = argparse.ArgumentParser(description="Автономный аудит контекста без Matreshka Agent")
    parser.add_argument("--project", default=".")
    parser.add_argument("--provider", choices=["none", "codex", "claude", "antigravity"], default="none")
    parser.add_argument("--telemetry-root")
    parser.add_argument("--save", action="store_true", help="Сохранить отчёт и состояние внутри проекта")
    parser.add_argument("--harness", choices=HARNESSES, default="codex")
    parser.add_argument("--approve", help="Точное подтверждение из предпросмотра remember")
    parser.add_argument("command", choices=["start", "adopt", "resume", "check", "status", "optimize", "finish", "remember"])
    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()
    try:
        if not root.is_dir():
            raise ValueError("Каталог проекта не найден.")
        if args.command == "remember":
            print(json.dumps(remember(root, args.harness, args.approve), ensure_ascii=False, indent=2))
            return 0
        if args.approve:
            raise ValueError("Подтверждение памяти применимо только к команде remember.")
        if args.command == "status":
            previous = read_latest(root)
            if previous:
                print("Сохранённое состояние, без нового аудита. Для обновления выполните check.\n")
                print(render(previous))
                return 0
        result = context_optimizer.run_command(args.command, root, provider=None if args.provider == "none" else args.provider,
            include_global=False, telemetry_root=args.telemetry_root, trigger_mode="STANDALONE", trigger_reason="Явный запрос пользователя", trigger_automatic=False)
        if args.command == "finish":
            result["comparison"] = compare_finish(read_latest(root, "baseline"), result)
        if args.save:
            locations = save_result(root, result)
            print(render(publication_copy(result, root)))
            print("Сохранено: " + locations["report"] + "\nЛокальные отчёты могут содержать приватные сведения. Не добавляйте .context-optimizer в Git.")
        else:
            print(render(publication_copy(result, root)))
            print("Файлы не изменялись. Для сохранения добавьте --save.")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print("Ошибка: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

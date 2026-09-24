#!/usr/bin/env python3
"""Локальная установка навыка. Только стандартная библиотека; без сети и запуска host.

Предпросмотр по умолчанию. Подтверждение привязано к пакету, пути и текущим файлам.
Обновление/удаление сохраняет прежнюю копию вне каталогов skills. Нет force-overwrite.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRODUCT = "matreshka-context-optimizer"
VERSION = "0.4.0-dev.2"
MANIFEST = ".context-install.json"
STATE = ".context-optimizer-installer"
LIMIT = 32 * 1024 * 1024
MAX_FILES = 2000
PROFILES = {
    "codex": (".agents/skills/context-optimizer", ".agents/skills/context-optimizer"),
    "claude": (".claude/skills/context-optimizer", ".claude/skills/context-optimizer"),
    "cursor": (".cursor/skills/context-optimizer", ".cursor/skills/context-optimizer"),
    "antigravity": (".agents/skills/context-optimizer", ".gemini/config/skills/context-optimizer"),
    "antigravity-cli": (".agents/skills/context-optimizer", ".gemini/antigravity-cli/skills/context-optimizer"),
}


class InstallError(ValueError):
    """Ошибка проверки; не повод обходить защиту."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def guarded(path: Path) -> Path:
    """Проверка компонентов ДО resolve, включая Windows reparse points в Python 3.11."""
    path = Path(os.path.abspath(path.expanduser()))
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InstallError(f"Ссылка или reparse point запрещены: {part}")
    return path


def anchor(path: Path) -> Path:
    # Системный /tmp на macOS может быть ссылкой. Выбранный корень канонизируем один раз.
    path = path.expanduser().absolute()
    if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
        raise InstallError("Выберите настоящий каталог, не ссылку/junction.")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise InstallError("Корневой каталог не найден.")
    return path


def destination(host: str, scope: str, project: Path, home: Path | None = None) -> tuple[Path, Path]:
    if host not in PROFILES or scope not in {"project", "user"}:
        raise InstallError("Неизвестная среда или область установки.")
    root = anchor(project if scope == "project" else (home or Path.home()))
    target = guarded(root / PROFILES[host][scope == "user"])
    return root, target


def walk_error(error: OSError) -> None:
    raise InstallError("Каталог пакета недоступен для чтения.") from error


def inventory(root: Path) -> tuple[dict[str, str], list[str]]:
    """Точная инвентаризация; непонятные файлы и ссылки не игнорируются."""
    guarded(root)
    files: dict[str, str] = {}
    directories: list[str] = []
    total = 0
    for current, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        for name in sorted(dirs):
            path = guarded(Path(current) / name)
            directories.append(path.relative_to(root).as_posix())
        for name in sorted(names):
            path = guarded(Path(current) / name)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                raise InstallError(f"Поддерживаются только обычные файлы без hardlink: {path}")
            total += info.st_size
            if total > LIMIT or len(files) >= MAX_FILES:
                raise InstallError("Размер установки превышает безопасный предел.")
            files[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return files, sorted(directories)


def snapshot(target: Path) -> tuple[str, dict[str, Any] | None]:
    guarded(target)
    if not target.exists():
        return "ABSENT", None
    if not target.is_dir():
        raise InstallError("Путь навыка занят не каталогом.")
    files, dirs = inventory(target)
    manifest_path = guarded(target / MANIFEST)
    if not manifest_path.is_file():
        raise InstallError("Папка уже существует без нашего manifest. Чужие файлы не заменяются.")
    if manifest_path.stat().st_size > 1024 * 1024:
        raise InstallError("Manifest слишком большой.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise InstallError("Manifest повреждён; автоматическая операция остановлена.") from exc
    if not isinstance(manifest, dict) or manifest.get("product") != PRODUCT or manifest.get("format") != 1:
        raise InstallError("Неизвестный manifest.")
    actual = {k: v for k, v in files.items() if k != MANIFEST}
    if actual != manifest.get("files") or dirs != manifest.get("directories"):
        raise InstallError("Установленные файлы изменены/добавлены/удалены. Сначала сохраните и разберите свои правки; принудительной замены нет.")
    if manifest.get("payload_sha256") != sha(encode(actual)):
        raise InstallError("Контрольная сумма manifest не совпала.")
    return sha(encode({"files": files, "directories": dirs})), manifest


def package(source: Path) -> dict[str, bytes]:
    source = anchor(source)
    nested = guarded(source / "skills/context-optimizer")
    if nested.is_dir():
        source = nested
    if not (source / "SKILL.md").is_file():
        raise InstallError("Источник не содержит SKILL.md.")
    result: dict[str, bytes] = {}
    total = 0
    for current, dirs, names in os.walk(source, followlinks=False, onerror=walk_error):
        # Сначала проверить ссылки, затем пропустить только известные временные каталоги.
        for name in dirs:
            guarded(Path(current) / name)
        dirs[:] = sorted(d for d in dirs if d not in {"__pycache__", ".git", ".context-optimizer"})
        for name in sorted(names):
            path = guarded(Path(current) / name)
            rel = path.relative_to(source).as_posix()
            if name.endswith((".pyc", ".pyo")) or name == MANIFEST:
                continue
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                raise InstallError("Источник содержит не обычный файл или hardlink.")
            total += info.st_size
            if total > LIMIT or len(result) >= MAX_FILES:
                raise InstallError("Пакет превышает безопасный предел.")
            result[rel] = path.read_bytes()
    for required in ("SKILL.md", "scripts/standalone.py", "scripts/context_optimizer.py", "scripts/quick.py", "LICENSE"):
        if required not in result:
            raise InstallError(f"Неполный пакет: нет {required}")
    if not re.search(rb"(?m)^name: context-optimizer\r?$", result["SKILL.md"]):
        raise InstallError("Имя навыка не совпало.")
    return result


def manifest_for(payload: dict[str, bytes]) -> dict[str, Any]:
    files = {k: sha(v) for k, v in sorted(payload.items())}
    dirs = sorted({str(parent).replace("\\", "/") for k in payload for parent in Path(k).parents if str(parent) != "."})
    return {"format": 1, "product": PRODUCT, "version": VERSION,
            "payload_sha256": sha(encode(files)), "files": files, "directories": dirs}


def plan(action: str, source: Path, target: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if action not in {"install", "update", "uninstall"}:
        raise InstallError("Операция не поддерживается.")
    before, old = snapshot(target)
    payload = {} if action == "uninstall" else package(source)
    incoming = manifest_for(payload) if payload else None
    if action == "update" and old is None:
        raise InstallError("Навык ещё не установлен. Используйте install.")
    if action == "install" and old and old["files"] != incoming["files"]:
        raise InstallError("Установлена другая версия. Используйте update.")
    unchanged = (action == "uninstall" and old is None) or (old is not None and incoming is not None and old["files"] == incoming["files"])
    basis = {"action": action, "target": str(target), "before": before, "after": incoming}
    result = {"action": action, "status": "UNCHANGED" if unchanged else "PREVIEW", "target": str(target),
              "files": len(payload) if payload else len((old or {}).get("files", {})),
              "version": (incoming or old or {}).get("version"), "before": before,
              "approval": "INSTALL-" + sha(encode(basis)),
              "message_ru": "Предпросмотр. Исходный проект, настройки приложений, разрешения и отчёты не меняются."}
    return result, payload


def atomic(path: Path, data: bytes) -> None:
    guarded(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def install_lock(root: Path):
    state = guarded(root / STATE)
    state.mkdir(exist_ok=True, mode=0o700)
    lock = guarded(state / "install.lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InstallError("Установщик занят. Не снимайте install.lock, пока не проверили активную операцию.") from exc
    try:
        os.close(fd)
        yield state
    finally:
        lock.unlink()


def pending(state: Path) -> list[str]:
    journal = guarded(state / "transactions")
    result = []
    if journal.exists():
        for path in journal.iterdir():
            guarded(path)
            if not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise InstallError("Некорректный журнал установки.")
            row = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(row, dict):
                raise InstallError("Журнал установки должен содержать объект.")
            if row.get("status") not in {"DONE", "ROLLED_BACK"}:
                result.append(str(path))
    return result


def apply(root: Path, target: Path, source: Path, action: str, approval: str) -> dict[str, Any]:
    preview, payload = plan(action, source, target)
    if preview["status"] == "UNCHANGED":
        return preview
    if approval != preview["approval"]:
        raise InstallError("Подтверждение устарело или относится к другому пакету/пути. Повторите предпросмотр.")
    with install_lock(root) as state:
        if pending(state):
            raise InstallError("Есть незавершённая транзакция. Восстановление требует проверки каталога backups/staging и журнала; автоматической перезаписи нет.")
        again, _ = plan(action, source, target)
        if again["approval"] != approval:
            raise InstallError("Файлы изменились между предпросмотром и блокировкой.")
        operation = uuid.uuid4().hex
        backup = guarded(state / "backups" / operation / "payload")
        stage = guarded(state / "staging" / operation)
        journal = guarded(state / "transactions" / (operation + ".json"))
        record = {"operation": action, "target": str(target), "backup": str(backup), "stage": str(stage),
                  "approval": approval, "before": preview["before"], "status": "PREPARING", "at": datetime.now(timezone.utc).isoformat()}
        atomic(journal, encode(record))
        moved = False
        activated = False
        try:
            if payload:
                stage.mkdir(parents=True, mode=0o700)
                for name, data in payload.items():
                    atomic(stage / name, data)
                atomic(stage / MANIFEST, encode(manifest_for(payload)))
                snapshot(stage)
            if snapshot(target)[0] != preview["before"]:
                raise InstallError("Установка изменилась во время подготовки.")
            guarded(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup.parent.mkdir(parents=True, mode=0o700)
                os.replace(target, backup)
                moved = True
            if payload:
                os.replace(stage, target)
            activated = True
            record["status"] = "DONE"
            atomic(journal, encode(record))
        except Exception as exc:
            # После активации не удаляем установленное: сбой журнала требует ручной сверки.
            if moved and not activated and not target.exists():
                os.replace(backup, target)
            record["status"] = "NEEDS_REVIEW" if activated else "ROLLED_BACK"
            try:
                atomic(journal, encode(record))
            except OSError:
                pass
            raise InstallError("Операция прервана. Исходные файлы сохранены; проверьте журнал: " + str(journal)) from exc
        return {**preview, "status": "APPLIED", "backup": str(backup) if moved else None,
                "journal": str(journal), "message_ru": "Готово. Обновите список навыков или перезапустите приложение. Аудиты и правила проекта сохранены."}


def doctor(root: Path, target: Path, host: str) -> dict[str, Any]:
    _, manifest = snapshot(target)
    unfinished = pending(root / STATE) if (root / STATE).exists() else []
    prefix = "$" if host == "codex" else "/"
    return {"status": "NEEDS_REVIEW" if unfinished else "INSTALLED" if manifest else "NOT_INSTALLED",
            "python": sys.version.split()[0], "target": str(target), "version": (manifest or {}).get("version"),
            "unfinished": unfinished, "quick_command": prefix + "context-optimizer help",
            "message_ru": "Проверены файлы, а не запущенный интерфейс приложения. Если команды не видны, перезапустите его. Локальная установка не устанавливает навык на удалённый сервер."}


def main() -> int:
    p = argparse.ArgumentParser(description="Установка Context Optimizer без сети: предпросмотр → подтверждение")
    p.add_argument("action", choices=["install", "update", "uninstall", "doctor"])
    p.add_argument("--host", choices=PROFILES, required=True)
    p.add_argument("--scope", choices=["project", "user"], default="project")
    p.add_argument("--project", default=".")
    p.add_argument("--source", default=str(Path(__file__).resolve().parent))
    p.add_argument("--approve", help="INSTALL-... из предпросмотра. Файлы не меняются без него.")
    args = p.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    try:
        if sys.version_info < (3, 11):
            raise InstallError("Нужен Python 3.11 или новее. Установите Python с python.org; установщик не делает это сам.")
        root, target = destination(args.host, args.scope, Path(args.project))
        if args.action == "doctor":
            result = doctor(root, target, args.host)
        elif args.approve:
            result = apply(root, target, Path(args.source), args.action, args.approve)
        else:
            result = plan(args.action, Path(args.source), target)[0]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print("Ошибка: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

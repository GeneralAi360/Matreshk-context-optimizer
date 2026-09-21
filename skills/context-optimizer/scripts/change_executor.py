#!/usr/bin/env python3
"""Reversible change executor for Context Optimizer.

Gate 8 principles:
- one change per invocation;
- dry-run before mutation;
- exact approval token;
- expected-before hash;
- backup before write/move;
- validation after change;
- rollback refuses to overwrite unrelated later changes.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from optimization_ledger import append_event


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()

STATE_DIR = ".context-optimizer"
SUPPORTED_OPERATIONS = {"REPLACE_EXACT_TEXT", "JSON_SET", "MOVE_PATH"}


class ChangeError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def hash_directory(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        if item.is_symlink():
            raise ChangeError(f"Symlink внутри MOVE_PATH directory не поддерживается: {item}")
        rel = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        file_hash = hash_file(item).encode("ascii")
        digest.update(file_hash)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if path.is_symlink():
        raise ChangeError(f"Mutation через symlink запрещён: {path}")
    if path.is_file():
        return hash_file(path)
    if path.is_dir():
        return hash_directory(path)
    raise ChangeError(f"Target не является file/directory: {path}")


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_user_path(
    project_root: Path,
    value: str,
    *,
    allow_global: bool,
    must_exist: bool = True,
) -> Path:
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else project_root / raw
    resolved = candidate.resolve(strict=must_exist)

    if not allow_global and not is_within(resolved, project_root):
        raise ChangeError(
            f"Target вне project root: {resolved}. Для global mutation нужен --allow-global."
        )
    if resolved == project_root:
        raise ChangeError("Mutation project root целиком запрещён")
    return resolved


def load_change(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeError(f"Не удалось прочитать change JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ChangeError("Change должен быть JSON object")

    required = {
        "change_id",
        "operation",
        "target",
        "expected_before_sha256",
        "source_finding_ids",
        "approval_required",
        "quality_risk",
        "params",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ChangeError("Change не содержит обязательные поля: " + ", ".join(missing))

    change_id = value.get("change_id")
    if not isinstance(change_id, str) or not change_id.startswith("CHG-"):
        raise ChangeError("Некорректный change_id")
    operation = value.get("operation")
    if operation not in SUPPORTED_OPERATIONS:
        raise ChangeError(f"Operation не поддерживается: {operation}")
    if value.get("approval_required") is not True:
        raise ChangeError("В Gate 8 каждый change обязан иметь approval_required=true")

    expected = value.get("expected_before_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ChangeError("expected_before_sha256 обязателен и должен быть SHA-256")
    return value


def state_root(project_root: Path) -> Path:
    return project_root / STATE_DIR


def journal_path(project_root: Path, change_id: str) -> Path:
    return state_root(project_root) / "journal" / f"{change_id}.json"


def backup_path(project_root: Path, change_id: str) -> Path:
    return state_root(project_root) / "backups" / change_id / "payload"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def copy_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ChangeError(f"Backup уже существует: {destination}")
    if source.is_file():
        shutil.copy2(source, destination)
    elif source.is_dir():
        shutil.copytree(source, destination)
    else:
        raise ChangeError(f"Невозможно backup target: {source}")


def restore_backup(backup: Path, target: Path) -> None:
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup.is_dir():
        shutil.copytree(backup, target)
    else:
        shutil.copy2(backup, target)


def text_after_replace(target: Path, params: dict[str, Any]) -> tuple[str, str]:
    try:
        before = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ChangeError(f"Target должен быть UTF-8 text file: {exc}") from exc

    old = params.get("old")
    new = params.get("new")
    expected_occurrences = params.get("expected_occurrences")
    if not isinstance(old, str) or not isinstance(new, str):
        raise ChangeError("REPLACE_EXACT_TEXT требует params.old/params.new strings")
    if not isinstance(expected_occurrences, int) or expected_occurrences < 1:
        raise ChangeError("expected_occurrences должен быть integer >= 1")

    actual = before.count(old)
    if actual != expected_occurrences:
        raise ChangeError(
            f"Exact text occurrences mismatch: expected={expected_occurrences}, actual={actual}"
        )
    return before, before.replace(old, new, expected_occurrences)


def json_set_after(target: Path, params: dict[str, Any]) -> tuple[str, str]:
    try:
        before = target.read_text(encoding="utf-8")
        data = json.loads(before)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChangeError(f"JSON_SET требует валидный UTF-8 JSON target: {exc}") from exc

    if not isinstance(data, dict):
        raise ChangeError("JSON_SET root должен быть object")

    key_path = params.get("path")
    if not isinstance(key_path, list) or not key_path or not all(
        isinstance(item, str) and item for item in key_path
    ):
        raise ChangeError("JSON_SET params.path должен быть непустым массивом строк")

    cursor: dict[str, Any] = data
    for key in key_path[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, dict):
            raise ChangeError(
                f"JSON_SET intermediate path отсутствует или не object: {key}"
            )
        cursor = next_value

    cursor[key_path[-1]] = params.get("value")
    after = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return before, after


def validate_text_result(
    target: Path,
    change: dict[str, Any],
) -> None:
    validation = change.get("validation")
    if not isinstance(validation, dict):
        validation = {}

    text = target.read_text(encoding="utf-8")

    if target.suffix.lower() == ".json":
        json.loads(text)

    for needle in validation.get("must_contain", []) or []:
        if isinstance(needle, str) and needle not in text:
            raise ChangeError(f"Validation failed: must_contain missing: {needle!r}")

    for needle in validation.get("must_not_contain", []) or []:
        if isinstance(needle, str) and needle in text:
            raise ChangeError(f"Validation failed: must_not_contain present: {needle!r}")


def unified_diff(before: str, after: str, target: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=target + ":before",
            tofile=target + ":after",
        )
    )


def prepare_change(
    project_root: Path,
    change: dict[str, Any],
    *,
    allow_global: bool,
) -> dict[str, Any]:
    target = resolve_user_path(
        project_root,
        str(change["target"]),
        allow_global=allow_global,
        must_exist=True,
    )
    before_hash = hash_path(target)
    if before_hash != change["expected_before_sha256"]:
        raise ChangeError(
            "Target hash mismatch. Change был подготовлен для другой версии файла/path."
        )

    operation = change["operation"]
    result: dict[str, Any] = {
        "change_id": change["change_id"],
        "operation": operation,
        "target": str(target),
        "before_sha256": before_hash,
        "finding_ids": list(change.get("source_finding_ids") or []),
        "quality_risk": change.get("quality_risk"),
    }

    params = change.get("params")
    if not isinstance(params, dict):
        raise ChangeError("params должен быть object")

    if operation == "REPLACE_EXACT_TEXT":
        before, after = text_after_replace(target, params)
        result["before_text"] = before
        result["after_text"] = after
        result["diff"] = unified_diff(before, after, str(target))
    elif operation == "JSON_SET":
        before, after = json_set_after(target, params)
        result["before_text"] = before
        result["after_text"] = after
        result["diff"] = unified_diff(before, after, str(target))
    elif operation == "MOVE_PATH":
        destination_value = params.get("destination")
        if not isinstance(destination_value, str) or not destination_value:
            raise ChangeError("MOVE_PATH требует params.destination")
        destination = resolve_user_path(
            project_root,
            destination_value,
            allow_global=allow_global,
            must_exist=False,
        )
        if destination.exists():
            raise ChangeError(f"MOVE_PATH destination уже существует: {destination}")
        if is_within(destination, target) if target.is_dir() else False:
            raise ChangeError("MOVE_PATH destination не может находиться внутри source")
        result["destination"] = str(destination)
    else:
        raise ChangeError(f"Unsupported operation: {operation}")

    return result


def dry_run(
    project_root: Path,
    change: dict[str, Any],
    *,
    allow_global: bool,
) -> dict[str, Any]:
    prepared = prepare_change(project_root, change, allow_global=allow_global)
    return {
        "mode": "DRY_RUN",
        "mutation": False,
        "approval_token_required_for_apply": change["change_id"],
        "prepared": {
            key: value
            for key, value in prepared.items()
            if key not in {"before_text", "after_text"}
        },
    }


def apply_change(
    project_root: Path,
    change: dict[str, Any],
    *,
    approval: str,
    allow_global: bool,
) -> dict[str, Any]:
    change_id = change["change_id"]
    if approval != change_id:
        raise ChangeError(
            f"Approval token mismatch. Для apply требуется --approve {change_id}"
        )

    journal = journal_path(project_root, change_id)
    if journal.exists():
        raise ChangeError(
            f"Journal для {change_id} уже существует. Change id нельзя переиспользовать."
        )

    prepared = prepare_change(project_root, change, allow_global=allow_global)
    target = Path(prepared["target"])
    backup = backup_path(project_root, change_id)
    copy_backup(target, backup)

    journal_record: dict[str, Any] = {
        "schema_version": "0.1",
        "change_id": change_id,
        "operation": change["operation"],
        "finding_ids": list(change.get("source_finding_ids") or []),
        "quality_risk": change.get("quality_risk"),
        "target": str(target),
        "destination": prepared.get("destination"),
        "backup": str(backup),
        "before_sha256": prepared["before_sha256"],
        "after_sha256": None,
        "status": "APPLYING",
        "applied_at": None,
        "rolled_back_at": None,
    }

    journal.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(journal, journal_record)

    try:
        if change["operation"] in {"REPLACE_EXACT_TEXT", "JSON_SET"}:
            atomic_write_text(target, prepared["after_text"])
            validate_text_result(target, change)
            after_hash = hash_path(target)
        elif change["operation"] == "MOVE_PATH":
            destination = Path(prepared["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(destination))
            after_hash = hash_path(destination)
        else:
            raise ChangeError("Unsupported operation")

        journal_record["after_sha256"] = after_hash
        journal_record["status"] = "APPLIED"
        journal_record["applied_at"] = now_iso()
        atomic_write_json(journal, journal_record)

        append_event(
            project_root,
            {
                "event_type": "APPLIED",
                "change_id": change_id,
                "status": "APPLIED",
                "finding_ids": list(change.get("source_finding_ids") or []),
                "target": str(target),
                "operation": change["operation"],
                "before": {
                    "sha256": prepared["before_sha256"],
                },
                "after": {
                    "sha256": after_hash,
                    "destination": prepared.get("destination"),
                },
                "notes": "Change applied after exact approval; quality verification still required.",
            },
        )

        return {
            "status": "APPLIED",
            "change_id": change_id,
            "target": str(target),
            "destination": prepared.get("destination"),
            "before_sha256": prepared["before_sha256"],
            "after_sha256": after_hash,
            "backup": str(backup),
            "journal": str(journal),
            "verification_required": True,
        }
    except Exception as exc:
        # Best-effort auto-restore. If restore itself fails, surface both errors.
        restore_error: str | None = None
        try:
            if change["operation"] == "MOVE_PATH":
                destination_value = prepared.get("destination")
                if destination_value:
                    destination = Path(destination_value)
                    if destination.exists():
                        if destination.is_dir():
                            shutil.rmtree(destination)
                        else:
                            destination.unlink()
            restore_backup(backup, target)
        except Exception as restore_exc:
            restore_error = str(restore_exc)

        journal_record["status"] = "FAILED"
        journal_record["failure"] = str(exc)
        journal_record["restore_error"] = restore_error
        atomic_write_json(journal, journal_record)

        try:
            append_event(
                project_root,
                {
                    "event_type": "APPLIED",
                    "change_id": change_id,
                    "status": "FAILED",
                    "finding_ids": list(change.get("source_finding_ids") or []),
                    "target": str(target),
                    "operation": change["operation"],
                    "before": {"sha256": prepared["before_sha256"]},
                    "after": None,
                    "notes": (
                        "Apply failed; auto-restore attempted. "
                        + (f"Restore error: {restore_error}" if restore_error else "Restore completed.")
                    ),
                },
            )
        except Exception:
            pass

        raise ChangeError(
            f"Apply failed: {exc}. "
            + (f"Auto-restore also failed: {restore_error}" if restore_error else "Auto-restore completed.")
        ) from exc


def load_journal(project_root: Path, change_id: str) -> dict[str, Any]:
    path = journal_path(project_root, change_id)
    if not path.exists():
        raise ChangeError(f"Journal не найден: {change_id}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeError(f"Journal повреждён: {exc}") from exc
    if not isinstance(value, dict):
        raise ChangeError("Journal должен быть JSON object")
    return value


def rollback_change(
    project_root: Path,
    change_id: str,
    *,
    approval: str,
    allow_global: bool,
) -> dict[str, Any]:
    expected_token = f"{change_id}:ROLLBACK"
    if approval != expected_token:
        raise ChangeError(
            f"Approval token mismatch. Для rollback требуется --approve {expected_token}"
        )

    journal_file = journal_path(project_root, change_id)
    journal = load_journal(project_root, change_id)

    if journal.get("status") != "APPLIED":
        raise ChangeError(
            f"Rollback разрешён только для status=APPLIED, текущий={journal.get('status')}"
        )

    target = resolve_user_path(
        project_root,
        str(journal["target"]),
        allow_global=allow_global,
        must_exist=journal.get("operation") != "MOVE_PATH",
    )
    backup = Path(str(journal["backup"])).resolve()
    if not backup.exists():
        raise ChangeError(f"Backup отсутствует: {backup}")

    operation = journal.get("operation")
    after_hash = journal.get("after_sha256")

    if operation in {"REPLACE_EXACT_TEXT", "JSON_SET"}:
        current_hash = hash_path(target)
        if current_hash != after_hash:
            raise ChangeError(
                "Target изменился после apply. Rollback остановлен, чтобы не затереть чужие изменения."
            )
        restore_backup(backup, target)
    elif operation == "MOVE_PATH":
        destination = resolve_user_path(
            project_root,
            str(journal["destination"]),
            allow_global=allow_global,
            must_exist=True,
        )
        current_hash = hash_path(destination)
        if current_hash != after_hash:
            raise ChangeError(
                "MOVE_PATH destination изменился после apply. Rollback остановлен."
            )
        if target.exists():
            raise ChangeError("Исходный target уже существует; rollback остановлен")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
        restore_backup(backup, target)
    else:
        raise ChangeError(f"Unsupported journal operation: {operation}")

    restored_hash = hash_path(target)
    if restored_hash != journal.get("before_sha256"):
        raise ChangeError("Rollback восстановил неожиданный hash; требуется ручная проверка")

    journal["status"] = "ROLLED_BACK"
    journal["rolled_back_at"] = now_iso()
    journal["restored_sha256"] = restored_hash
    atomic_write_json(journal_file, journal)

    append_event(
        project_root,
        {
            "event_type": "ROLLED_BACK",
            "change_id": change_id,
            "status": "ROLLED_BACK",
            "finding_ids": list(journal.get("finding_ids") or []),
            "target": str(target),
            "operation": str(operation),
            "before": {"sha256": after_hash},
            "after": {"sha256": restored_hash},
            "notes": "Rollback выполнен только после проверки current hash.",
        },
    )

    return {
        "status": "ROLLED_BACK",
        "change_id": change_id,
        "target": str(target),
        "restored_sha256": restored_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Context Optimizer reversible change executor")
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument(
        "--allow-global",
        action="store_true",
        help="Разрешить target вне project root. Approval всё равно обязателен.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run")
    dry.add_argument("--change", required=True)

    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--change", required=True)
    apply_parser.add_argument("--approve", required=True)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--change-id", required=True)
    rollback.add_argument("--approve", required=True)

    status = sub.add_parser("status")
    status.add_argument("--change-id", required=True)

    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()

    try:
        if args.command in {"dry-run", "apply"}:
            change = load_change(Path(args.change).expanduser().resolve())
            if args.command == "dry-run":
                result = dry_run(root, change, allow_global=args.allow_global)
            else:
                result = apply_change(
                    root,
                    change,
                    approval=args.approve,
                    allow_global=args.allow_global,
                )
        elif args.command == "rollback":
            result = rollback_change(
                root,
                args.change_id,
                approval=args.approve,
                allow_global=args.allow_global,
            )
        else:
            result = load_journal(root, args.change_id)
    except (ChangeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Безопасное применение одного обратимого изменения Context Optimizer.

Инварианты:
- один change за вызов;
- dry-run не пишет проект;
- approval привязан к точному change + текущему target + результату preview;
- backup проверяется до mutation и перед rollback;
- target/state не проходят через symlink/junction;
- rollback не затирает последующие изменения;
- quality verification отделена от факта APPLY.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from optimization_ledger import append_event
from quality_verifier import evaluate_runs, load_object as load_benchmark_object, record_change_verification


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()

STATE_DIR = ".context-optimizer"
RESERVED_TOP_LEVEL = {".git", STATE_DIR, ".context-optimizer-installer"}
SUPPORTED_OPERATIONS = {"REPLACE_EXACT_TEXT", "JSON_SET", "MOVE_PATH"}
CHANGE_ID_RE = re.compile(r"^CHG-[0-9]{3,}$")
FINDING_ID_RE = re.compile(r"^CTX-[0-9]{3,}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
ALLOWED_TOP_LEVEL = {
    "change_id",
    "operation",
    "target",
    "expected_before_sha256",
    "source_finding_ids",
    "approval_required",
    "quality_risk",
    "params",
    "validation",
}
ROLLBACKABLE_STATUSES = {
    "APPLIED",
    "VERIFIED_KEEP",
    "ROLLBACK_RECOMMENDED",
    "NEEDS_MORE_DATA",
}


class ChangeError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _lexical_candidate(boundary: Path, raw: Path) -> Path:
    if any(part == ".." for part in raw.parts):
        raise ChangeError("Путь с '..' запрещён для mutation.")
    if raw.is_absolute():
        return raw
    return boundary / raw


def _reject_link_chain(boundary: Path, candidate: Path) -> None:
    boundary = boundary.expanduser().absolute()
    candidate = candidate.expanduser().absolute()
    try:
        rel = candidate.relative_to(boundary)
    except ValueError as exc:
        raise ChangeError(f"Путь вне разрешённой области: {candidate}") from exc

    cursor = boundary
    if _is_link(cursor):
        raise ChangeError(f"Корень разрешённой области является link/junction: {cursor}")
    for part in rel.parts:
        cursor = cursor / part
        if cursor.exists() and _is_link(cursor):
            raise ChangeError(f"Mutation через symlink/junction запрещён: {cursor}")


def _boundary_for(project_root: Path, candidate: Path, allow_global: bool) -> Path:
    project = project_root.expanduser().resolve()
    candidate_abs = candidate.expanduser().absolute()

    try:
        candidate_abs.relative_to(project)
        return project
    except ValueError:
        pass

    if not allow_global:
        raise ChangeError(
            f"Target вне project root: {candidate_abs}. Для user-scope mutation нужен --allow-global."
        )

    home = Path.home().expanduser().resolve()
    try:
        candidate_abs.relative_to(home)
    except ValueError as exc:
        raise ChangeError(
            "Даже с --allow-global mutation разрешён только внутри домашней папки пользователя."
        ) from exc
    return home


def _reject_reserved(project_root: Path, resolved: Path) -> None:
    project = project_root.expanduser().resolve()
    try:
        rel = resolved.relative_to(project)
    except ValueError:
        return
    if rel.parts and rel.parts[0] in RESERVED_TOP_LEVEL:
        raise ChangeError(
            f"Mutation служебной области {rel.parts[0]!r} запрещён через change executor."
        )


def resolve_user_path(
    project_root: Path,
    value: str,
    *,
    allow_global: bool,
    must_exist: bool = True,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ChangeError("Пустой target path запрещён.")

    raw = Path(value.strip()).expanduser()
    base = project_root.expanduser().resolve() if not raw.is_absolute() else Path("/")
    candidate = _lexical_candidate(base, raw)
    boundary = _boundary_for(project_root, candidate, allow_global)
    _reject_link_chain(boundary, candidate)

    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise ChangeError(f"Target не найден: {candidate}") from exc

    if resolved == project_root.expanduser().resolve():
        raise ChangeError("Mutation project root целиком запрещён.")
    _reject_reserved(project_root, resolved)
    return resolved


def ensure_state_root(project_root: Path) -> Path:
    root = project_root.expanduser().resolve()
    state = root / STATE_DIR
    if state.exists() and _is_link(state):
        raise ChangeError("Служебная папка .context-optimizer не может быть symlink/junction.")
    state.mkdir(parents=True, exist_ok=True)
    if _is_link(state):
        raise ChangeError("Служебная папка .context-optimizer неожиданно стала link/junction.")
    return state


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
    entries = sorted(path.rglob("*"), key=lambda p: p.relative_to(path).as_posix())
    for item in entries:
        if _is_link(item):
            raise ChangeError(f"Symlink/junction внутри directory target запрещён: {item}")
        rel = item.relative_to(path).as_posix().encode("utf-8")
        marker = b"D" if item.is_dir() else b"F" if item.is_file() else b"X"
        digest.update(marker)
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        if item.is_file():
            digest.update(hash_file(item).encode("ascii"))
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if _is_link(path):
        raise ChangeError(f"Mutation через symlink/junction запрещён: {path}")
    if path.is_file():
        return hash_file(path)
    if path.is_dir():
        return hash_directory(path)
    raise ChangeError(f"Target не является file/directory: {path}")


def validate_change(value: dict[str, Any]) -> None:
    unknown = sorted(set(value) - ALLOWED_TOP_LEVEL)
    if unknown:
        raise ChangeError("Неизвестные поля change: " + ", ".join(unknown))

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
    if not isinstance(change_id, str) or not CHANGE_ID_RE.fullmatch(change_id):
        raise ChangeError("change_id должен иметь формат CHG-001 или выше.")

    operation = value.get("operation")
    if operation not in SUPPORTED_OPERATIONS:
        raise ChangeError(f"Operation не поддерживается: {operation!r}")

    if value.get("approval_required") is not True:
        raise ChangeError("Каждый change обязан иметь approval_required=true.")

    expected = value.get("expected_before_sha256")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise ChangeError("expected_before_sha256 должен быть lowercase SHA-256.")

    findings = value.get("source_finding_ids")
    if (
        not isinstance(findings, list)
        or not findings
        or not all(isinstance(x, str) and FINDING_ID_RE.fullmatch(x) for x in findings)
    ):
        raise ChangeError("source_finding_ids должен содержать минимум один CTX-xxx.")

    if value.get("quality_risk") not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        raise ChangeError("quality_risk имеет неизвестное значение.")

    params = value.get("params")
    if not isinstance(params, dict):
        raise ChangeError("params должен быть object.")

    validation = value.get("validation", {})
    if not isinstance(validation, dict):
        raise ChangeError("validation должен быть object.")
    unknown_validation = set(validation) - {"must_contain", "must_not_contain"}
    if unknown_validation:
        raise ChangeError(
            "Неизвестные validation поля: " + ", ".join(sorted(unknown_validation))
        )
    for key in ("must_contain", "must_not_contain"):
        values = validation.get(key, [])
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise ChangeError(f"validation.{key} должен быть массивом строк.")

    if operation == "REPLACE_EXACT_TEXT":
        if set(params) != {"old", "new", "expected_occurrences"}:
            raise ChangeError(
                "REPLACE_EXACT_TEXT принимает только old/new/expected_occurrences."
            )
        old, new = params.get("old"), params.get("new")
        count = params.get("expected_occurrences")
        if not isinstance(old, str) or not old:
            raise ChangeError("params.old должен быть непустой строкой.")
        if not isinstance(new, str):
            raise ChangeError("params.new должен быть строкой.")
        if old == new:
            raise ChangeError("REPLACE_EXACT_TEXT не должен заменять текст самим собой.")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000:
            raise ChangeError("expected_occurrences должен быть integer 1..1000.")

    elif operation == "JSON_SET":
        if set(params) != {"path", "value"}:
            raise ChangeError("JSON_SET принимает только path/value.")
        key_path = params.get("path")
        if (
            not isinstance(key_path, list)
            or not key_path
            or len(key_path) > 64
            or not all(isinstance(x, str) and x and len(x) <= 256 for x in key_path)
        ):
            raise ChangeError("JSON_SET path должен быть непустым массивом коротких строк.")
        try:
            canonical(params.get("value"))
        except (TypeError, ValueError) as exc:
            raise ChangeError("JSON_SET value должен быть JSON-совместимым.") from exc

    elif operation == "MOVE_PATH":
        if set(params) != {"destination"}:
            raise ChangeError("MOVE_PATH принимает только destination.")
        destination = params.get("destination")
        if not isinstance(destination, str) or not destination.strip():
            raise ChangeError("MOVE_PATH destination должен быть непустой строкой.")


def load_change(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeError(f"Не удалось прочитать change JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ChangeError("Change должен быть JSON object.")
    validate_change(value)
    return value


def state_root(project_root: Path) -> Path:
    return project_root.expanduser().resolve() / STATE_DIR


def journal_path(project_root: Path, change_id: str) -> Path:
    return state_root(project_root) / "journal" / f"{change_id}.json"


def backup_path(project_root: Path, change_id: str) -> Path:
    return state_root(project_root) / "backups" / change_id / "payload"


def lock_path(project_root: Path, change_id: str) -> Path:
    return state_root(project_root) / "change-locks" / f"{change_id}.lock"


@contextlib.contextmanager
def change_lock(project_root: Path, change_id: str):
    ensure_state_root(project_root)
    path = lock_path(project_root, change_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_link(path.parent):
        raise ChangeError("Папка change-locks не может быть link/junction.")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ChangeError(
            f"Change {change_id} уже обрабатывается. Проверьте {path}; "
            "автоматическое снятие lock запрещено."
        ) from exc
    try:
        os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
        os.close(fd)
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
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


def copy_backup(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ChangeError(f"Backup уже существует: {destination}")
    if source.is_file():
        shutil.copy2(source, destination)
    elif source.is_dir():
        shutil.copytree(source, destination)
    else:
        raise ChangeError(f"Невозможно backup target: {source}")
    return hash_path(destination)


def remove_backup_container(backup: Path) -> None:
    root = backup.parent
    if root.exists():
        shutil.rmtree(root)


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


def read_utf8_exact(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ChangeError(f"Target должен быть UTF-8 text file: {exc}") from exc


def text_after_replace(target: Path, params: dict[str, Any]) -> tuple[str, str]:
    before = read_utf8_exact(target)
    old = params["old"]
    new = params["new"]
    expected_occurrences = params["expected_occurrences"]
    actual = before.count(old)
    if actual != expected_occurrences:
        raise ChangeError(
            f"Exact text occurrences mismatch: expected={expected_occurrences}, actual={actual}"
        )
    return before, before.replace(old, new, expected_occurrences)


def json_set_after(target: Path, params: dict[str, Any]) -> tuple[str, str]:
    before = read_utf8_exact(target)
    try:
        data = json.loads(before)
    except json.JSONDecodeError as exc:
        raise ChangeError(f"JSON_SET требует валидный JSON target: {exc}") from exc
    if not isinstance(data, dict):
        raise ChangeError("JSON_SET root должен быть object.")

    cursor: dict[str, Any] = data
    key_path = params["path"]
    for key in key_path[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, dict):
            raise ChangeError(
                f"JSON_SET intermediate path отсутствует или не object: {key}"
            )
        cursor = next_value

    cursor[key_path[-1]] = params["value"]
    trailing = "\n" if before.endswith(("\n", "\r")) else ""
    after = json.dumps(data, ensure_ascii=False, indent=2) + trailing
    return before, after


def validate_text_result(target: Path, change: dict[str, Any]) -> None:
    validation = change.get("validation") or {}
    text = read_utf8_exact(target)

    if target.suffix.lower() == ".json":
        json.loads(text)

    for needle in validation.get("must_contain", []):
        if needle not in text:
            raise ChangeError(f"Validation failed: must_contain missing: {needle!r}")

    for needle in validation.get("must_not_contain", []):
        if needle in text:
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


def prepared_after_hash(prepared: dict[str, Any]) -> str:
    if "after_text" in prepared:
        return sha256_bytes(prepared["after_text"].encode("utf-8"))
    return sha256_bytes(
        canonical(
            {
                "operation": prepared["operation"],
                "target": prepared["target"],
                "destination": prepared.get("destination"),
                "before_sha256": prepared["before_sha256"],
            }
        )
    )


def change_fingerprint(change: dict[str, Any], prepared: dict[str, Any]) -> str:
    material = {
        "change": change,
        "resolved_target": prepared["target"],
        "resolved_destination": prepared.get("destination"),
        "before_sha256": prepared["before_sha256"],
        "preview_after_sha256": prepared_after_hash(prepared),
    }
    return sha256_bytes(canonical(material))


def apply_approval_token(change: dict[str, Any], prepared: dict[str, Any]) -> str:
    return "APPLY-" + change_fingerprint(change, prepared)[:32]


def rollback_approval_token(journal: dict[str, Any]) -> str:
    material = {
        "change_id": journal.get("change_id"),
        "operation": journal.get("operation"),
        "target": journal.get("target"),
        "destination": journal.get("destination"),
        "before_sha256": journal.get("before_sha256"),
        "after_sha256": journal.get("after_sha256"),
        "backup_sha256": journal.get("backup_sha256"),
    }
    return "ROLLBACK-" + sha256_bytes(canonical(material))[:32]


def prepare_change(
    project_root: Path,
    change: dict[str, Any],
    *,
    allow_global: bool,
) -> dict[str, Any]:
    validate_change(change)
    target = resolve_user_path(
        project_root,
        str(change["target"]),
        allow_global=allow_global,
        must_exist=True,
    )
    before_hash = hash_path(target)
    if before_hash != change["expected_before_sha256"]:
        raise ChangeError(
            "Target hash mismatch. Change был подготовлен для другой версии target."
        )

    result: dict[str, Any] = {
        "change_id": change["change_id"],
        "operation": change["operation"],
        "target": str(target),
        "before_sha256": before_hash,
        "finding_ids": list(change["source_finding_ids"]),
        "quality_risk": change["quality_risk"],
    }

    params = change["params"]
    if change["operation"] == "REPLACE_EXACT_TEXT":
        before, after = text_after_replace(target, params)
        result["before_text"] = before
        result["after_text"] = after
        result["diff"] = unified_diff(before, after, str(target))

    elif change["operation"] == "JSON_SET":
        before, after = json_set_after(target, params)
        result["before_text"] = before
        result["after_text"] = after
        result["diff"] = unified_diff(before, after, str(target))

    elif change["operation"] == "MOVE_PATH":
        destination = resolve_user_path(
            project_root,
            str(params["destination"]),
            allow_global=allow_global,
            must_exist=False,
        )
        if destination.exists():
            raise ChangeError(f"MOVE_PATH destination уже существует: {destination}")
        if destination == target:
            raise ChangeError("MOVE_PATH source и destination совпадают.")
        if target.is_dir():
            try:
                destination.relative_to(target)
                raise ChangeError(
                    "MOVE_PATH destination не может находиться внутри source directory."
                )
            except ValueError:
                pass
        result["destination"] = str(destination)

    return result


def dry_run(
    project_root: Path,
    change: dict[str, Any],
    *,
    allow_global: bool,
) -> dict[str, Any]:
    prepared = prepare_change(project_root, change, allow_global=allow_global)
    token = apply_approval_token(change, prepared)
    return {
        "mode": "DRY_RUN",
        "mutation": False,
        "change_fingerprint": change_fingerprint(change, prepared),
        "approval_token_required_for_apply": token,
        "prepared": {
            key: value
            for key, value in prepared.items()
            if key not in {"before_text", "after_text"}
        },
    }


def verify_backup_integrity(backup: Path, expected: str) -> str:
    if not backup.exists():
        raise ChangeError(f"Backup отсутствует: {backup}")
    if _is_link(backup):
        raise ChangeError("Backup неожиданно является symlink/junction.")
    actual = hash_path(backup)
    if actual != expected:
        raise ChangeError(
            "Backup повреждён: его SHA-256 не совпадает с исходным target. "
            "Автоматический rollback запрещён."
        )
    return actual


def apply_change(
    project_root: Path,
    change: dict[str, Any],
    *,
    approval: str,
    allow_global: bool,
) -> dict[str, Any]:
    change_id = change["change_id"]

    with change_lock(project_root, change_id):
        journal = journal_path(project_root, change_id)
        if journal.exists():
            raise ChangeError(
                f"Journal для {change_id} уже существует. Change id нельзя переиспользовать."
            )

        prepared = prepare_change(project_root, change, allow_global=allow_global)
        expected_approval = apply_approval_token(change, prepared)
        if approval != expected_approval:
            raise ChangeError(
                "Approval token mismatch. Сначала повторите dry-run и подтвердите "
                "точный APPLY-токен из актуального preview."
            )

        target = Path(prepared["target"])
        backup = backup_path(project_root, change_id)
        if backup.parent.exists() and _is_link(backup.parent):
            raise ChangeError("Backup directory не может быть symlink/junction.")

        backup_hash = copy_backup(target, backup)
        if backup_hash != prepared["before_sha256"]:
            remove_backup_container(backup)
            raise ChangeError(
                "Backup не совпал с исходным target. Mutation не выполнялась."
            )

        # Закрывает окно между preview/backup и mutation.
        if hash_path(target) != prepared["before_sha256"]:
            remove_backup_container(backup)
            raise ChangeError(
                "Target изменился во время подготовки. Mutation остановлена; повторите dry-run."
            )

        journal_record: dict[str, Any] = {
            "schema_version": "0.2",
            "change_id": change_id,
            "operation": change["operation"],
            "change_fingerprint": change_fingerprint(change, prepared),
            "finding_ids": list(change["source_finding_ids"]),
            "quality_risk": change["quality_risk"],
            "target": str(target),
            "destination": prepared.get("destination"),
            "backup": str(backup),
            "backup_sha256": backup_hash,
            "before_sha256": prepared["before_sha256"],
            "preview_after_sha256": prepared_after_hash(prepared),
            "after_sha256": None,
            "status": "APPLYING",
            "applied_at": None,
            "rolled_back_at": None,
            "verification": None,
        }

        journal.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(journal, journal_record)

        try:
            if change["operation"] in {"REPLACE_EXACT_TEXT", "JSON_SET"}:
                atomic_write_text(target, prepared["after_text"])
                validate_text_result(target, change)
                after_hash = hash_path(target)
                if after_hash != prepared["preview_after_sha256"]:
                    raise ChangeError(
                        "Фактический результат не совпадает с подтверждённым preview."
                    )

            elif change["operation"] == "MOVE_PATH":
                destination = Path(prepared["destination"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                if _is_link(destination.parent):
                    raise ChangeError(
                        "Destination parent неожиданно стал symlink/junction."
                    )
                shutil.move(str(target), str(destination))
                after_hash = hash_path(destination)

            else:
                raise ChangeError("Unsupported operation.")

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
                    "finding_ids": list(change["source_finding_ids"]),
                    "target": str(target),
                    "operation": change["operation"],
                    "before": {
                        "sha256": prepared["before_sha256"],
                        "backup_sha256": backup_hash,
                    },
                    "after": {
                        "sha256": after_hash,
                        "destination": prepared.get("destination"),
                    },
                    "notes": (
                        "Change применён по content-bound approval. "
                        "Quality verification ещё обязательна."
                    ),
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
                "backup_sha256": backup_hash,
                "journal": str(journal),
                "verification_required": True,
                "rollback_approval_token": rollback_approval_token(journal_record),
            }

        except Exception as exc:
            restore_error: str | None = None
            try:
                verify_backup_integrity(backup, prepared["before_sha256"])
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
                if hash_path(target) != prepared["before_sha256"]:
                    raise ChangeError("Auto-restore вернул неожиданный SHA-256.")
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
                        "finding_ids": list(change["source_finding_ids"]),
                        "target": str(target),
                        "operation": change["operation"],
                        "before": {"sha256": prepared["before_sha256"]},
                        "after": None,
                        "notes": (
                            "Apply failed; auto-restore attempted. "
                            + (
                                f"Restore error: {restore_error}"
                                if restore_error
                                else "Restore completed and hash verified."
                            )
                        ),
                    },
                )
            except Exception:
                pass

            raise ChangeError(
                f"Apply failed: {exc}. "
                + (
                    f"Auto-restore also failed: {restore_error}"
                    if restore_error
                    else "Auto-restore completed and verified."
                )
            ) from exc


def load_journal(project_root: Path, change_id: str) -> dict[str, Any]:
    if not CHANGE_ID_RE.fullmatch(change_id):
        raise ChangeError("Некорректный change_id.")
    path = journal_path(project_root, change_id)
    if not path.exists():
        raise ChangeError(f"Journal не найден: {change_id}")
    if _is_link(path):
        raise ChangeError("Journal не может быть symlink/junction.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeError(f"Journal повреждён: {exc}") from exc
    if not isinstance(value, dict):
        raise ChangeError("Journal должен быть JSON object.")
    return value


def current_after_path(journal: dict[str, Any]) -> Path:
    if journal.get("operation") == "MOVE_PATH":
        return Path(str(journal.get("destination")))
    return Path(str(journal.get("target")))


def structural_integrity(project_root: Path, journal: dict[str, Any]) -> dict[str, Any]:
    after_path = current_after_path(journal)
    expected_after = journal.get("after_sha256")
    backup = Path(str(journal.get("backup")))
    expected_before = str(journal.get("before_sha256"))
    backup_ok = False
    current_ok = False
    errors: list[str] = []

    try:
        verify_backup_integrity(backup, expected_before)
        backup_ok = True
    except ChangeError as exc:
        errors.append(str(exc))

    try:
        current_ok = (
            after_path.exists()
            and isinstance(expected_after, str)
            and hash_path(after_path) == expected_after
        )
        if not current_ok:
            errors.append(
                "Текущий target/destination уже не совпадает с состоянием сразу после apply."
            )
    except ChangeError as exc:
        errors.append(str(exc))

    return {
        "backup_integrity": backup_ok,
        "current_after_integrity": current_ok,
        "errors": errors,
    }


def rollback_change(
    project_root: Path,
    change_id: str,
    *,
    approval: str,
    allow_global: bool,
) -> dict[str, Any]:
    with change_lock(project_root, change_id):
        journal_file = journal_path(project_root, change_id)
        journal = load_journal(project_root, change_id)

        if journal.get("status") not in ROLLBACKABLE_STATUSES:
            raise ChangeError(
                "Rollback разрешён только после APPLIED/verification состояния; "
                f"текущий status={journal.get('status')!r}."
            )

        expected_token = rollback_approval_token(journal)
        if approval != expected_token:
            raise ChangeError(
                "Rollback approval mismatch. Получите актуальный token через status/verify."
            )

        target = resolve_user_path(
            project_root,
            str(journal["target"]),
            allow_global=allow_global,
            must_exist=journal.get("operation") != "MOVE_PATH",
        )
        backup = Path(str(journal["backup"])).resolve()
        expected_before = str(journal.get("before_sha256"))
        expected_backup = str(journal.get("backup_sha256") or expected_before)

        backup_hash = verify_backup_integrity(backup, expected_before)
        if backup_hash != expected_backup:
            raise ChangeError("Backup hash не совпадает с journal; rollback запрещён.")

        operation = journal.get("operation")
        after_hash = journal.get("after_sha256")

        if operation in {"REPLACE_EXACT_TEXT", "JSON_SET"}:
            if hash_path(target) != after_hash:
                raise ChangeError(
                    "Target изменился после apply. Rollback остановлен, чтобы не затереть новые изменения."
                )
            restore_backup(backup, target)

        elif operation == "MOVE_PATH":
            destination = resolve_user_path(
                project_root,
                str(journal["destination"]),
                allow_global=allow_global,
                must_exist=True,
            )
            if hash_path(destination) != after_hash:
                raise ChangeError(
                    "MOVE_PATH destination изменился после apply. Rollback остановлен."
                )
            if target.exists():
                raise ChangeError("Исходный target уже существует; rollback остановлен.")
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
            restore_backup(backup, target)

        else:
            raise ChangeError(f"Unsupported journal operation: {operation}")

        restored_hash = hash_path(target)
        if restored_hash != expected_before:
            raise ChangeError(
                "Rollback восстановил неожиданный hash; требуется ручная проверка."
            )

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
                "notes": "Rollback выполнен после проверки current и backup hash.",
            },
        )

        return {
            "status": "ROLLED_BACK",
            "change_id": change_id,
            "target": str(target),
            "restored_sha256": restored_hash,
        }


def verify_change(
    project_root: Path,
    change_id: str,
    *,
    before_run: Path,
    after_run: Path,
) -> dict[str, Any]:
    with change_lock(project_root, change_id):
        journal_file = journal_path(project_root, change_id)
        journal = load_journal(project_root, change_id)
        if journal.get("status") not in ROLLBACKABLE_STATUSES:
            raise ChangeError(
                f"Quality verification недоступна при status={journal.get('status')!r}."
            )

        integrity = structural_integrity(project_root, journal)
        if not integrity["backup_integrity"] or not integrity["current_after_integrity"]:
            journal["status"] = "NEEDS_MANUAL_REVIEW"
            journal["verification"] = {
                "verdict": "UNVERIFIED",
                "integrity": integrity,
                "verified_at": now_iso(),
            }
            atomic_write_json(journal_file, journal)
            raise ChangeError(
                "Structural integrity не подтверждена. Автоматическая оценка качества остановлена."
            )

        result = evaluate_runs(
            load_benchmark_object(before_run),
            load_benchmark_object(after_run),
        )
        event = record_change_verification(
            project_root,
            change_id,
            list(journal.get("finding_ids") or []),
            result,
        )

        verdict = result["verdict"]
        if verdict == "PASS":
            status = "VERIFIED_KEEP"
        elif verdict == "FAIL":
            status = "ROLLBACK_RECOMMENDED"
        else:
            status = "NEEDS_MORE_DATA"

        journal["status"] = status
        journal["verification"] = {
            "verdict": verdict,
            "result": result,
            "ledger_event_id": event.get("event_id"),
            "verified_at": now_iso(),
        }
        atomic_write_json(journal_file, journal)

        return {
            "status": status,
            "change_id": change_id,
            "verification": result,
            "integrity": integrity,
            "rollback_approval_token": (
                rollback_approval_token(journal)
                if status == "ROLLBACK_RECOMMENDED"
                else None
            ),
        }


def status_change(project_root: Path, change_id: str) -> dict[str, Any]:
    journal = load_journal(project_root, change_id)
    integrity = (
        structural_integrity(project_root, journal)
        if journal.get("status") in ROLLBACKABLE_STATUSES
        else None
    )
    result = dict(journal)
    result["integrity"] = integrity
    result["rollback_approval_token"] = (
        rollback_approval_token(journal)
        if journal.get("status") in ROLLBACKABLE_STATUSES
        else None
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Context Optimizer reversible change executor"
    )
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument(
        "--allow-global",
        action="store_true",
        help=(
            "Разрешить user-scope target вне project root, но только внутри home. "
            "Approval всё равно обязателен."
        ),
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

    verify = sub.add_parser("verify")
    verify.add_argument("--change-id", required=True)
    verify.add_argument("--before", required=True)
    verify.add_argument("--after", required=True)

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
        elif args.command == "verify":
            result = verify_change(
                root,
                args.change_id,
                before_run=Path(args.before).expanduser().resolve(),
                after_run=Path(args.after).expanduser().resolve(),
            )
        else:
            result = status_change(root, args.change_id)

    except (
        ChangeError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

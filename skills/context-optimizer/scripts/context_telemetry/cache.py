from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import Any

CACHE_VERSION = 2


def default_cache_dir() -> Path:
    override = os.environ.get("MATRESHKA_CONTEXT_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system().lower()
    home = Path.home()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return base / "Matreshka" / "context-optimizer" / "cache"
    if system == "darwin":
        return home / "Library" / "Caches" / "matreshka-context-optimizer"
    return Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "matreshka-context-optimizer"


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": CACHE_VERSION, "files": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "files": {}}
    if not isinstance(value, dict) or value.get("version") != CACHE_VERSION or not isinstance(value.get("files"), dict):
        return {"version": CACHE_VERSION, "files": {}}
    return value


def save_cache(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def cache_hit(cache: dict[str, Any], file_path: Path, fp: dict[str, Any]) -> dict[str, Any] | None:
    files = cache.get("files")
    if not isinstance(files, dict):
        return None
    item = files.get(str(file_path.resolve()))
    if not isinstance(item, dict):
        return None
    if item.get("mtime_ns") != fp.get("mtime_ns") or item.get("size_bytes") != fp.get("size_bytes"):
        return None
    result = item.get("result")
    return result if isinstance(result, dict) else None


def cache_put(cache: dict[str, Any], file_path: Path, fp: dict[str, Any], result: dict[str, Any]) -> None:
    files = cache.setdefault("files", {})
    files[str(file_path.resolve())] = {
        "mtime_ns": fp.get("mtime_ns"),
        "size_bytes": fp.get("size_bytes"),
        "result": result,
    }

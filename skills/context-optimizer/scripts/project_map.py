#!/usr/bin/env python3
"""Нативная карта проекта без внешних зависимостей."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build",
    ".next", ".venv", "venv", "__pycache__", ".context-optimizer",
    ".matreshka/runs",
}
SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs",
    ".java", ".kt", ".kts", ".cs", ".cpp", ".cc", ".c", ".h", ".hpp",
    ".php", ".rb", ".swift", ".vue", ".svelte", ".sql", ".sh", ".ps1",
}
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}
CONFIG_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
}
TEST_MARKERS = {"test", "tests", "__tests__", "spec", "specs", "e2e"}


def _skip(rel_parts: tuple[str, ...]) -> bool:
    joined = "/".join(rel_parts)
    return any(
        part in SKIP_DIRS or joined.startswith(item + "/")
        for part in rel_parts
        for item in SKIP_DIRS
    )


def _kind(path: Path) -> str:
    lower_parts = {p.lower() for p in path.parts}
    if lower_parts & TEST_MARKERS or path.name.lower().startswith(("test_", "spec_")):
        return "test"
    if path.suffix.lower() in SOURCE_EXTENSIONS:
        return "source"
    if path.suffix.lower() in DOC_EXTENSIONS:
        return "docs"
    if path.name in CONFIG_NAMES:
        return "config"
    return "other"


def build_project_map(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Корень проекта не существует: {root}")

    files: list[dict[str, Any]] = []
    areas: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    extensions: Counter[str] = Counter()
    total_bytes = 0

    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        try:
            rel_dir = current_path.relative_to(root)
        except ValueError:
            continue
        dirs[:] = [
            d for d in dirs
            if not _skip(tuple((rel_dir / d).parts))
        ]

        for name in names:
            path = current_path / name
            try:
                rel = path.relative_to(root)
                stat = path.stat()
            except (OSError, ValueError):
                continue
            if _skip(tuple(rel.parts)):
                continue

            area = rel.parts[0] if len(rel.parts) > 1 else "."
            kind = _kind(rel)
            ext = path.suffix.lower() or "<none>"
            total_bytes += int(stat.st_size)
            areas[area] += 1
            kinds[kind] += 1
            extensions[ext] += 1
            files.append({
                "path": rel.as_posix(),
                "area": area,
                "kind": kind,
                "bytes": int(stat.st_size),
            })

    file_count = len(files)
    area_count = len(areas)

    if file_count >= 1200 or area_count >= 24 or total_bytes >= 40 * 1024 * 1024:
        pressure = "HIGH"
        reason = "Большой проект: навигацию нужно выполнять через карту областей и точечное чтение файлов."
    elif file_count >= 250 or area_count >= 10 or total_bytes >= 8 * 1024 * 1024:
        pressure = "MEDIUM"
        reason = "Средний проект: сначала выбирать область по карте, затем читать только релевантные файлы."
    else:
        pressure = "LOW"
        reason = "Проект небольшой; отдельная навигационная оптимизация обычно не требуется."

    top_areas = [
        {"name": name, "files": count}
        for name, count in areas.most_common(12)
    ]
    top_extensions = [
        {"extension": ext, "files": count}
        for ext, count in extensions.most_common(12)
    ]

    return {
        "schema_version": "0.1",
        "mode": "READ_ONLY",
        "project_root": str(root),
        "state": "READY",
        "file_count": file_count,
        "total_bytes": total_bytes,
        "area_count": area_count,
        "navigation_pressure": pressure,
        "reason": reason,
        "kinds": dict(kinds),
        "top_areas": top_areas,
        "top_extensions": top_extensions,
        "routing_rule": (
            "Сначала определить область по карте проекта; затем читать минимальный набор файлов. "
            "Повторное широкое сканирование допустимо только при изменении карты или недостаточном evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Нативная read-only карта проекта")
    parser.add_argument("--project", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = build_project_map(Path(args.project))
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

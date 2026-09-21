#!/usr/bin/env python3
"""Read-only environment scanner for Matreshka Context Optimizer v0.1."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Iterable

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
}

INSTRUCTION_NAMES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
PROJECT_SKILL_ROOTS = (
    (".agents/skills", "codex"),
    (".claude/skills", "claude"),
    (".gemini/skills", "gemini"),
)
GLOBAL_SKILL_ROOTS = (
    (".agents/skills", "codex"),
    (".claude/skills", "claude"),
    (".gemini/skills", "gemini"),
)


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def walk_project(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".cache")]
        current_path = Path(current)
        for name in files:
            yield current_path / name


def file_record(path: Path, root: Path, scope: str, kind: str) -> dict:
    stat = path.stat()
    return {
        "path": rel(path, root),
        "absolute_path": str(path.resolve()),
        "scope": scope,
        "kind": kind,
        "bytes": stat.st_size,
    }


def discover_instruction_files(root: Path) -> list[dict]:
    records = []
    for path in walk_project(root):
        if path.name in INSTRUCTION_NAMES:
            records.append(file_record(path, root, "PROJECT", "instruction"))
    return sorted(records, key=lambda x: x["path"])


def discover_skills(root: Path, include_global: bool) -> list[dict]:
    records: list[dict] = []

    def collect(base: Path, scope: str, host: str) -> None:
        if not base.exists():
            return
        for skill_file in sorted(base.glob("*/SKILL.md")):
            record = file_record(skill_file, root, scope, "skill")
            record["host"] = host
            record["skill_name"] = skill_file.parent.name
            records.append(record)

    for rel_root, host in PROJECT_SKILL_ROOTS:
        collect(root / rel_root, "PROJECT", host)

    if include_global:
        home = Path.home()
        for rel_root, host in GLOBAL_SKILL_ROOTS:
            collect(home / rel_root, "GLOBAL", host)

    return records


def discover_configs(root: Path) -> list[dict]:
    candidates = [
        root / ".mcp.json",
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
        root / ".codex" / "config.toml",
        root / ".gemini" / "settings.json",
    ]
    return [
        file_record(path, root, "PROJECT", "config")
        for path in candidates
        if path.exists() and path.is_file()
    ]


def cli_state(name: str) -> dict:
    path = shutil.which(name)
    return {"available": bool(path), "path": path}


def build_report(root: Path, include_global: bool) -> dict:
    instructions = discover_instruction_files(root)
    skills = discover_skills(root, include_global=include_global)
    configs = discover_configs(root)

    graph_path = root / "graphify-out" / "graph.json"

    capabilities = {
        "PROJECT_INSTRUCTIONS_DISCOVERY": "SUPPORTED",
        "SKILL_DISCOVERY": "SUPPORTED",
        "MCP_DISCOVERY": "PARTIAL" if any(x["path"].endswith(".mcp.json") for x in configs) else "UNKNOWN",
        "SESSION_USAGE_COUNTERS": "UNKNOWN",
        "SESSION_CONTEXT_TREE": "UNKNOWN",
        "LOCAL_TRANSCRIPTS": "UNKNOWN",
        "HOOK_DISCOVERY": "UNKNOWN",
        "REPOSITORY_GRAPH_NAVIGATION": "SUPPORTED" if graph_path.exists() else "UNKNOWN",
        "EXTERNAL_CLI": "SUPPORTED",
        "ROLLBACK_SUPPORT": "UNSUPPORTED",
    }

    return {
        "schema_version": "0.1",
        "mode": "READ_ONLY",
        "project_root": str(root.resolve()),
        "environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python": platform.python_version(),
            "instructions": instructions,
            "skills": skills,
            "configs": configs,
            "external_tools": {
                "codeburn": cli_state("codeburn"),
                "caveman": cli_state("caveman"),
                "graphify": cli_state("graphify"),
            },
            "graphify": {
                "graph_exists": graph_path.exists(),
                "graph_path": str(graph_path.resolve()) if graph_path.exists() else None,
            },
        },
        "capabilities": capabilities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Context Optimizer environment scan")
    parser.add_argument("--project", default=".", help="Project root")
    parser.add_argument(
        "--include-global",
        action="store_true",
        help="Also inventory supported global skill roots. No files are modified.",
    )
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root does not exist or is not a directory: {root}")

    print(json.dumps(build_report(root, args.include_global), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

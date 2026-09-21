#!/usr/bin/env python3
"""Graphify Adapter для Context Optimizer v0.1.

По умолчанию adapter работает read-only:
- обнаруживает Graphify и существующий graph;
- оценивает, есть ли основания рекомендовать graph-first navigation;
- строит план установки/сборки/обновления, но не выполняет mutation;
- может выполнять только read-only graphify query по уже существующему graph.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "graphify-out",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".context-optimizer",
}

SOURCE_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".kts", ".cs", ".cpp", ".cc", ".c",
    ".h", ".hpp", ".rb", ".php", ".swift", ".scala", ".lua", ".dart",
    ".vue", ".svelte", ".html", ".css", ".scss", ".sql", ".graphql",
    ".md", ".mdx", ".txt", ".toml", ".yaml", ".yml", ".json",
}

SUPPORTED_PLATFORMS = {"codex", "claude", "antigravity", "agents"}

NAVIGATION_EVIDENCE_MARKERS = (
    "REREAD",
    "RE_READ",
    "REDUNDANT_REREADS",
    "NAVIGATION",
    "WARMUP_HEAVY",
    "REPOSITORY_GRAPH",
)


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()


class GraphifyAdapterError(RuntimeError):
    pass


def graphify_path() -> str | None:
    return shutil.which("graphify")


def graphify_version(timeout: int = 15) -> str | None:
    executable = graphify_path()
    if not executable:
        return None
    proc = subprocess.run(
        [executable, "--version"],
        cwd=None,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or proc.stderr.strip() or None


def iter_source_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [
            name for name in dirs
            if name not in SKIP_DIRS and not name.startswith(".cache")
        ]
        current_path = Path(current)
        for name in files:
            path = current_path / name
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                yield path


def project_profile(root: Path) -> dict[str, Any]:
    count = 0
    total_bytes = 0
    newest_mtime = 0.0
    newest_path: str | None = None

    for path in iter_source_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        count += 1
        total_bytes += stat.st_size
        if stat.st_mtime > newest_mtime:
            newest_mtime = stat.st_mtime
            try:
                newest_path = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                newest_path = str(path.resolve())

    return {
        "source_files": count,
        "source_bytes": total_bytes,
        "newest_source_mtime": newest_mtime or None,
        "newest_source_path": newest_path,
    }


def graph_stats(graph_path: Path) -> dict[str, Any]:
    if not graph_path.exists():
        return {
            "exists": False,
            "path": str(graph_path.resolve()),
            "bytes": 0,
            "mtime": None,
            "nodes": None,
            "edges": None,
        }

    try:
        stat = graph_path.stat()
    except OSError:
        return {
            "exists": True,
            "path": str(graph_path.resolve()),
            "bytes": None,
            "mtime": None,
            "nodes": None,
            "edges": None,
        }

    nodes = None
    edges = None
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            raw_nodes = data.get("nodes")
            raw_edges = data.get("edges")
            if raw_edges is None:
                raw_edges = data.get("links")
            if isinstance(raw_nodes, (list, dict)):
                nodes = len(raw_nodes)
            if isinstance(raw_edges, (list, dict)):
                edges = len(raw_edges)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass

    return {
        "exists": True,
        "path": str(graph_path.resolve()),
        "bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "nodes": nodes,
        "edges": edges,
    }


def platform_artifacts(root: Path, platform: str) -> list[Path]:
    if platform == "claude":
        return [
            root / ".claude" / "skills" / "graphify" / "SKILL.md",
        ]
    if platform == "codex":
        return [
            root / ".agents" / "skills" / "graphify" / "SKILL.md",
        ]
    if platform == "antigravity":
        return [
            root / ".agents" / "skills" / "graphify" / "SKILL.md",
            root / ".agents" / "rules" / "graphify.md",
            root / ".agents" / "workflows" / "graphify.md",
        ]
    if platform == "agents":
        return [
            root / ".agents" / "skills" / "graphify" / "SKILL.md",
        ]
    raise GraphifyAdapterError(f"Неподдерживаемая platform: {platform}")


def installation_state(root: Path, platform: str) -> dict[str, Any]:
    artifacts = platform_artifacts(root, platform)
    rows = [
        {
            "path": str(path.resolve()),
            "exists": path.exists(),
        }
        for path in artifacts
    ]
    present = sum(1 for row in rows if row["exists"])
    if present == len(rows):
        state = "INSTALLED"
    elif present == 0:
        state = "NOT_INSTALLED"
    else:
        state = "PARTIAL"
    return {
        "state": state,
        "artifacts": rows,
    }


def load_evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphifyAdapterError(f"Не удалось прочитать evidence JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GraphifyAdapterError("Evidence должен быть JSON object")
    return value


def navigation_evidence(evidence: dict[str, Any] | None) -> list[str]:
    if not evidence:
        return []
    findings = evidence.get("findings")
    if not isinstance(findings, list):
        return []

    hits: list[str] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").upper()
        if any(marker in category for marker in NAVIGATION_EVIDENCE_MARKERS):
            hits.append(category)
            continue

        problem = item.get("problem")
        if isinstance(problem, dict):
            combined = " ".join(
                str(problem.get(key) or "") for key in ("title", "description")
            ).upper()
            if "RE-READ" in combined or ("ПОВТОР" in combined and "ФАЙЛ" in combined):
                hits.append(category or "TEXT_EVIDENCE")
    return sorted(set(hits))


def freshness_signal(profile: dict[str, Any], graph: dict[str, Any]) -> str:
    if not graph.get("exists"):
        return "NO_GRAPH"
    graph_mtime = graph.get("mtime")
    newest_source = profile.get("newest_source_mtime")
    if not isinstance(graph_mtime, (int, float)) or not isinstance(newest_source, (int, float)):
        return "UNKNOWN"
    if newest_source > graph_mtime:
        return "POSSIBLY_STALE"
    return "NO_NEWER_SOURCE_MTIME"


def recommend(
    status: dict[str, Any],
    *,
    min_files: int = 200,
    min_bytes: int = 2_000_000,
    evidence_hits: list[str] | None = None,
) -> dict[str, Any]:
    evidence_hits = evidence_hits or []
    graph = status["graph"]
    profile = status["project_profile"]
    cli = status["cli"]
    freshness = status["freshness"]

    reasons: list[str] = []
    basis = "HEURISTIC_ESTIMATE"

    if graph["exists"]:
        if freshness == "POSSIBLY_STALE":
            return {
                "action": "UPDATE_RECOMMENDED",
                "confidence": "MEDIUM",
                "basis": "TOOL_MEASURED",
                "reasons": [
                    "graphify-out/graph.json существует",
                    "обнаружен project source file новее graph.json по mtime",
                ],
            }
        return {
            "action": "USE_EXISTING_GRAPH",
            "confidence": "HIGH",
            "basis": "TOOL_MEASURED",
            "reasons": ["graphify-out/graph.json уже существует"],
        }

    if evidence_hits:
        reasons.append("найдены navigation/re-read findings: " + ", ".join(evidence_hits))
        basis = "TOOL_MEASURED"

    if profile["source_files"] >= min_files:
        reasons.append(
            f"source_files={profile['source_files']} >= heuristic threshold {min_files}"
        )
    if profile["source_bytes"] >= min_bytes:
        reasons.append(
            f"source_bytes={profile['source_bytes']} >= heuristic threshold {min_bytes}"
        )

    if reasons:
        if cli["available"]:
            action = "BUILD_RECOMMENDED"
        else:
            action = "INSTALL_RECOMMENDED"
        return {
            "action": action,
            "confidence": "MEDIUM" if evidence_hits else "LOW",
            "basis": basis,
            "reasons": reasons,
        }

    return {
        "action": "NOT_NEEDED_BY_CURRENT_EVIDENCE",
        "confidence": "LOW",
        "basis": "HEURISTIC_ESTIMATE",
        "reasons": [
            "нет готового graph",
            "не обнаружены navigation findings",
            "project не превысил configured size thresholds",
        ],
    }


def build_status(
    root: Path,
    *,
    platform: str,
    evidence: dict[str, Any] | None = None,
    min_files: int = 200,
    min_bytes: int = 2_000_000,
) -> dict[str, Any]:
    if platform not in SUPPORTED_PLATFORMS:
        raise GraphifyAdapterError(
            f"platform должна быть одной из: {', '.join(sorted(SUPPORTED_PLATFORMS))}"
        )

    profile = project_profile(root)
    graph = graph_stats(root / "graphify-out" / "graph.json")
    install = installation_state(root, platform)
    executable = graphify_path()
    version = graphify_version() if executable else None
    hits = navigation_evidence(evidence)

    status = {
        "adapter": "graphify",
        "adapter_mode": "READ_ONLY",
        "project_root": str(root.resolve()),
        "platform": platform,
        "cli": {
            "available": bool(executable),
            "path": executable,
            "version": version,
            "official_package": "graphifyy",
            "official_repository": "https://github.com/Graphify-Labs/graphify",
        },
        "project_install": install,
        "graph": graph,
        "project_profile": profile,
        "freshness": freshness_signal(profile, graph),
        "evidence_hits": hits,
        "thresholds": {
            "min_files": min_files,
            "min_bytes": min_bytes,
            "type": "HEURISTIC_ESTIMATE",
        },
    }
    status["recommendation"] = recommend(
        status,
        min_files=min_files,
        min_bytes=min_bytes,
        evidence_hits=hits,
    )
    return status


def project_install_command(platform: str) -> list[str]:
    if platform == "claude":
        return ["graphify", "install", "--project"]
    if platform == "codex":
        return ["graphify", "install", "--project", "--platform", "codex"]
    if platform == "antigravity":
        return ["graphify", "install", "--project", "--platform", "antigravity"]
    if platform == "agents":
        return ["graphify", "install", "--project", "--platform", "agents"]
    raise GraphifyAdapterError(f"Неподдерживаемая platform: {platform}")


def build_plan(status: dict[str, Any]) -> dict[str, Any]:
    platform = status["platform"]
    cli_available = bool(status["cli"]["available"])
    graph_exists = bool(status["graph"]["exists"])
    install_state = status["project_install"]["state"]

    steps: list[dict[str, Any]] = []

    if not cli_available:
        steps.append(
            {
                "id": "INSTALL_PACKAGE",
                "mutation": True,
                "approval_required": True,
                "preferred_command": ["uv", "tool", "install", "graphifyy"],
                "alternatives": [
                    ["pipx", "install", "graphifyy"],
                    [sys.executable, "-m", "pip", "install", "graphifyy"],
                ],
                "note": "Официальный PyPI package — graphifyy; CLI command — graphify.",
            }
        )

    if install_state != "INSTALLED":
        steps.append(
            {
                "id": "REGISTER_PROJECT_SKILL",
                "mutation": True,
                "approval_required": True,
                "command": project_install_command(platform),
                "note": "Project-scoped registration. Не выполнять без approval.",
            }
        )

    if not graph_exists:
        steps.append(
            {
                "id": "BUILD_GRAPH",
                "mutation": True,
                "approval_required": True,
                "command": ["graphify", "."],
                "note": "Создаёт graphify-out/ и graph.json. Выполнять только если recommendation это оправдывает.",
            }
        )
    elif status["freshness"] == "POSSIBLY_STALE":
        steps.append(
            {
                "id": "UPDATE_GRAPH",
                "mutation": True,
                "approval_required": True,
                "command": ["graphify", "update"],
                "note": "mtime — только stale signal; перед update стоит подтвердить релевантность изменений.",
            }
        )

    if graph_exists:
        steps.append(
            {
                "id": "USE_GRAPH_FIRST",
                "mutation": False,
                "approval_required": False,
                "command_template": ["graphify", "query", "<question>", "--budget", "2000"],
                "note": "Для вопроса по codebase сначала query graph, затем читать только target files.",
            }
        )

    return {
        "adapter": "graphify",
        "adapter_mode": "PLAN_ONLY",
        "recommendation": status["recommendation"],
        "steps": steps,
        "automatic_execution": False,
        "approval_policy": "Каждый mutation step требует отдельного approval перед выполнением.",
    }


def run_query(
    root: Path,
    question: str,
    *,
    budget: int = 2000,
    dfs: bool = False,
    timeout: int = 60,
) -> dict[str, Any]:
    executable = graphify_path()
    if not executable:
        raise GraphifyAdapterError("Graphify CLI не найден в PATH")

    graph = root / "graphify-out" / "graph.json"
    if not graph.exists():
        raise GraphifyAdapterError("graphify-out/graph.json не найден; query без graph запрещён")

    if budget <= 0:
        raise GraphifyAdapterError("budget должен быть > 0")

    args = [executable, "query", question, "--budget", str(budget)]
    if dfs:
        args.append("--dfs")

    proc = subprocess.run(
        args,
        cwd=str(root),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"exit={proc.returncode}"
        raise GraphifyAdapterError(message)

    return {
        "adapter": "graphify",
        "adapter_mode": "READ_ONLY_QUERY",
        "project_root": str(root.resolve()),
        "question": question,
        "budget": budget,
        "mode": "DFS" if dfs else "BFS",
        "tool_version": graphify_version(),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Graphify Adapter для Context Optimizer")
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument(
        "--platform",
        default="codex",
        choices=sorted(SUPPORTED_PLATFORMS),
    )
    parser.add_argument("--evidence", help="Audit/CodeBurn JSON для evidence-based recommendation")
    parser.add_argument("--min-files", type=int, default=200)
    parser.add_argument("--min-bytes", type=int, default=2_000_000)
    parser.add_argument("--timeout", type=int, default=60)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("plan")

    query = subparsers.add_parser("query")
    query.add_argument("--question", required=True)
    query.add_argument("--budget", type=int, default=2000)
    query.add_argument("--dfs", action="store_true")

    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root не существует: {root}")

    try:
        evidence = load_evidence(
            Path(args.evidence).expanduser().resolve() if args.evidence else None
        )

        if args.command == "query":
            result = run_query(
                root,
                args.question,
                budget=args.budget,
                dfs=args.dfs,
                timeout=args.timeout,
            )
        else:
            status = build_status(
                root,
                platform=args.platform,
                evidence=evidence,
                min_files=args.min_files,
                min_bytes=args.min_bytes,
            )
            result = status if args.command == "status" else build_plan(status)
    except (GraphifyAdapterError, subprocess.TimeoutExpired) as exc:
        print(
            json.dumps(
                {
                    "adapter": "graphify",
                    "status": "UNAVAILABLE",
                    "error": str(exc),
                },
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
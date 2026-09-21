#!/usr/bin/env python3
"""Smoke test for safe native Antigravity SQLite decoding."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from context_telemetry import antigravity


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def key(number: int, wire: int) -> bytes:
    return varint((number << 3) | wire)


def vint(number: int, value: int) -> bytes:
    return key(number, 0) + varint(value)


def blob(number: int, value: bytes) -> bytes:
    return key(number, 2) + varint(len(value)) + value


def text(number: int, value: str) -> bytes:
    return blob(number, value.encode("utf-8"))


def usage(input_tokens: int, response: int, thinking: int, response_id: str) -> bytes:
    total_output = response + thinking
    return (
        vint(2, input_tokens)
        + vint(3, total_output)
        + vint(9, response)
        + vint(10, thinking)
        + text(11, response_id)
    )


def chat(input_tokens: int, response: int, thinking: int, response_id: str, ts: int) -> bytes:
    timestamp = vint(1, ts)
    start_meta = blob(4, timestamp)
    return (
        blob(4, usage(input_tokens, response, thinking, response_id))
        + blob(9, start_meta)
        + text(19, "gemini-test")
        + text(21, "Gemini Test")
    )


def generation(
    input_tokens: int,
    response: int,
    thinking: int,
    response_id: str,
    ts: int,
    step_indices: list[int],
) -> bytes:
    packed = b"".join(varint(idx) for idx in step_indices)
    return blob(1, chat(input_tokens, response, thinking, response_id, ts)) + blob(2, packed)


def tool_step(name: str, arguments: dict) -> bytes:
    tool = text(2, name) + text(3, json.dumps(arguments, ensure_ascii=False))
    return blob(4, tool)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        db.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, status INTEGER, metadata BLOB)")
        db.execute("CREATE TABLE trajectory_metadata_blob (data BLOB)")
        db.execute(
            "INSERT INTO gen_metadata(idx, data) VALUES (?, ?)",
            (0, generation(100, 20, 10, "resp-1", 1789984800, [1])),
        )
        db.execute(
            "INSERT INTO gen_metadata(idx, data) VALUES (?, ?)",
            (1, generation(200, 30, 10, "resp-2", 1789984860, [2])),
        )
        # Duplicate response id must be ignored.
        db.execute(
            "INSERT INTO gen_metadata(idx, data) VALUES (?, ?)",
            (2, generation(999, 99, 1, "resp-2", 1789984920, [2])),
        )
        db.execute(
            "INSERT INTO steps(idx, step_type, status, metadata) VALUES (?, ?, ?, ?)",
            (1, 1, 3, tool_step("view_file", {"AbsolutePath": "/work/proj/.agents/skills/demo/SKILL.md"})),
        )
        db.execute(
            "INSERT INTO steps(idx, step_type, status, metadata) VALUES (?, ?, ?, ?)",
            (2, 1, 3, tool_step("call_mcp_tool", {"ServerName": "github", "ToolName": "search"})),
        )
        db.execute(
            "INSERT INTO trajectory_metadata_blob(data) VALUES (?)",
            (b"workspace file:///work/proj extra",),
        )
        db.commit()
    finally:
        db.close()


def main() -> int:
    wrapper = SCRIPT_DIR / "native_telemetry.py"

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        db_path = home / ".gemini" / "antigravity-ide" / "conversations" / "cascade-1.db"
        make_db(db_path)
        before = sha256(db_path)

        session = antigravity.parse_sqlite_file(db_path, project_hint="antigravity-ide")
        after = sha256(db_path)

        assert before == after
        assert session["usage"]["measurement_type"] == "PROVIDER_MEASURED"
        assert session["usage"]["measured_calls"] == 2
        assert session["usage"]["input_tokens"] == 300
        assert session["usage"]["output_tokens"] == 50
        assert session["usage"]["reasoning_output_tokens"] == 20
        assert session["usage"]["total_tokens"] == 370
        assert session["context"]["reported_context_tokens"] == 200
        assert session["context"]["reported_context_semantics"] == "LAST_GENERATION_INPUT"
        assert session["model"] == "gemini-test"
        assert session["project"] == "proj"
        assert "demo" in session["events"]["skills"]
        assert "mcp__github__search" in session["events"]["mcp_tools"]
        assert session["safety"]["rpc"] is False
        assert session["safety"]["database_write"] is False
        assert not db_path.with_suffix(".db-journal").exists()

        proc = subprocess.run(
            [
                sys.executable,
                str(wrapper),
                "--provider",
                "antigravity",
                "--root",
                str(home),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        report = json.loads(proc.stdout)
        assert report["capability"] == "SAFE_SQLITE_NATIVE"
        assert report["usage"]["input_tokens"] == 300
        assert report["usage"]["total_tokens"] == 370
        assert report["safety"]["network"] is False
        assert report["safety"]["process_probe"] is False
        assert report["safety"]["rpc"] is False
        assert sha256(db_path) == before

    print("PASS: Antigravity safe SQLite smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

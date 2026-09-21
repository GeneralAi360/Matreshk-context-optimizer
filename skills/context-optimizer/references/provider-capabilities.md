# Capability model платформ

## Правило

Нельзя считать capability доступной только по названию harness. В начале run optimizer проверяет фактические локальные данные и возможности.

## Capabilities

~~~text
SESSION_USAGE_COUNTERS
CURRENT_CONTEXT_MEASUREMENT
LOCAL_TRANSCRIPTS
SKILL_DISCOVERY
MCP_DISCOVERY
TOOL_SCHEMA_DISCOVERY
PROJECT_INSTRUCTIONS_DISCOVERY
GLOBAL_INSTRUCTIONS_DISCOVERY
SUBAGENT_USAGE
NATIVE_PROJECT_MAP
ROLLBACK_SUPPORT
~~~

Каждая capability: `SUPPORTED | PARTIAL | UNSUPPORTED | UNKNOWN`.

## Codex

- local rollout discovery;
- provider token counters;
- current-context semantics только когда конкретный event их доказывает;
- file/tool/skill/MCP event extraction;
- project/global skill discovery.

## Claude Code

- local JSONL discovery;
- provider-measured assistant usage;
- cache read/create counters;
- tool/read/skill/MCP extraction;
- cross-file resumed-session dedup пока `PARTIAL`.

## Antigravity

- read-only SQLite conversation decoding;
- provider-measured generation usage;
- referenced tool/MCP/skill steps;
- existing statusline parsing;
- legacy `.pb` sources пока `PARTIAL`;
- process scanning, live RPC и hook install не требуются для штатного режима.

## Неизвестные данные

Если runtime context нельзя доказать, использовать `UNKNOWN`. Нельзя выводить число из bytes, времени, количества сообщений или размера context window.

## Навигация

`NATIVE_PROJECT_MAP` строит карту областей/файлов и выбирает LOW/MEDIUM/HIGH navigation pressure. Она не даёт прав на изменение проекта.

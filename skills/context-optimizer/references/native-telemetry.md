# Native Matreshka Context Telemetry

## Цель

`Matreshka Context Telemetry` — собственный read-only слой измерения runtime/session данных. Для штатной работы ему не нужны сторонние оптимизаторы.

## Codex

- `$CODEX_HOME` или `~/.codex`;
- `sessions/YYYY/MM/DD/rollout-*.jsonl` и archived sessions;
- structural validation `session_meta`;
- provider-measured token events;
- cumulative/dedup guards;
- reasoning не суммируется поверх output;
- current context только когда event действительно содержит per-request usage;
- exact bytes composition;
- file/skill/MCP/tool events.

## Claude Code

- local JSONL discovery;
- provider-measured `message.usage`;
- cache read/create/input/output;
- message-id dedup внутри session file;
- tool/read/skill/MCP extraction;
- cross-file resume hardening ещё продолжается.

## Antigravity

- `.gemini/antigravity*` discovery;
- read-only SQLite `.db` через built-in `sqlite3`;
- минимальный protobuf-wire decoder для нужных полей;
- provider-measured generation usage;
- tool/MCP/skill extraction;
- optional existing statusline parsing;
- legacy `.pb` пока static-only.

SQLite открывается `mode=ro` + `PRAGMA query_only=ON`.

## Безопасность по умолчанию

~~~text
NETWORK = OFF
PROCESS_PROBE = OFF
RPC = OFF
HOOK_INSTALL = OFF
SESSION_FILE_WRITE = OFF
CACHE = OFF
~~~

Cache включается только явным `--use-cache` и хранится вне project/session roots.

## Использование

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider codex
python skills/context-optimizer/scripts/native_telemetry.py --provider claude
python skills/context-optimizer/scripts/native_telemetry.py --provider antigravity
~~~

## Measurement semantics

- provider token counters → `PROVIDER_MEASURED`;
- exact composition → bytes;
- aggregate spend не переименовывается в current context;
- неизвестное остаётся `UNKNOWN`;
- static bytes не переводятся в runtime tokens.

## Provenance

Реализация — `INDEPENDENT_IMPLEMENTATION`; provider-specific форматы защищены тестами и fail-closed поведением при неизвестной структуре.

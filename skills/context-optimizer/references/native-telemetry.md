# Native Matreshka Context Telemetry

## Цель

`Matreshka Context Telemetry` — собственный read-only слой измерения runtime/session данных. Он заменяет CodeBurn как обязательную telemetry dependency.

CodeBurn остаётся внешним референсом, optional compatibility layer и test oracle. Для штатной работы native telemetry CodeBurn не нужен.

## Поддержка v0.2

### Codex — PRIMARY / SUPPORTED

- discovery из `$CODEX_HOME` или `~/.codex`;
- строгий `sessions/YYYY/MM/DD/rollout-*.jsonl` + `archived_sessions/`;
- structural validation первого `session_meta`;
- provider-measured `token_count` parsing;
- `last_token_usage` и cumulative fallback;
- duplicate/equal-cumulative guards;
- reasoning не суммируется поверх output;
- current-context только когда конкретный event реально содержит per-request usage;
- exact bytes breakdown по system/user/developer/assistant/tool-call/tool-result/compaction;
- file-read / skill / MCP/tool extraction;
- native waste findings;
- optional external cache, выключенный по умолчанию.

### Claude Code — SUPPORTED / LIMITED

- local JSONL discovery;
- provider-measured assistant `message.usage`;
- cache-read/cache-create/input/output accounting;
- message-id dedup внутри session file;
- tool / Read / Skill / MCP extraction;
- exact bytes breakdown.

Ограничение v0.2: cross-file streaming-message dedup между несколькими resumed files ещё не считается FULL guarantee. При спорной ситуации provider state должен быть PARTIAL, а не выдумываться.

### Antigravity — SAFE PARTIAL

- статическое обнаружение `.gemini/antigravity*` conversation sources;
- optional parsing уже существующего statusline JSONL;
- **нет** live process probe;
- **нет** `ps/lsof`/PowerShell process scanning;
- **нет** локального HTTPS/RPC;
- **нет** отключения TLS verification;
- **нет** hook install;
- **нет** записи в conversation DB/PB.

Прямой безопасный DB/PB decoder можно добавить позже независимо, после отдельного fixture/eval пакета.

## Безопасность

Native telemetry по умолчанию:

~~~text
NETWORK = OFF
PROCESS_PROBE = OFF
RPC = OFF
HOOK_INSTALL = OFF
SESSION_FILE_WRITE = OFF
CACHE = OFF
~~~

Cache включается только явным `--use-cache` и хранится вне project/session roots. Базовая директория выбирается из user cache location или `MATRESHKA_CONTEXT_CACHE_DIR`.

## Использование

### Codex

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider codex
~~~

Конкретная session:

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider codex --session-prefix <id>
~~~

### Claude

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider claude
~~~

### Antigravity

Без statusline native engine делает только безопасный static discovery:

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider antigravity
~~~

Если уже существует trusted statusline JSONL:

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider antigravity --statusline <file>
~~~

## Measurement semantics

- provider token counters → `PROVIDER_MEASURED`;
- exact text/tool composition → bytes, не tokens;
- если per-request current context неизвестен после cumulative-only event — `UNKNOWN`, даже если session spend известен точно;
- aggregate spend никогда не переименовывается в current context;
- static bytes никогда не переводятся в runtime tokens.

## CodeBurn oracle

Для разработки можно сравнить одну Codex session с заранее созданным CodeBurn `context --json` report:

~~~bash
python evals/compare_codeburn_context_oracle.py --native native.json --codeburn codeburn-context.json --session-prefix <id>
~~~

Comparator ничего не устанавливает и не запускает. Он использует CodeBurn только как optional test oracle.

## Provenance

Реализация — `INDEPENDENT_IMPLEMENTATION`. CodeBurn использовался как документированный технический референс и источник edge-case идей; runtime код CodeBurn внутрь native engine не vendor'ится.

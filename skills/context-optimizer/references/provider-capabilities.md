# Capability model платформ

Этот файл описывает не обещания платформ, а способ работы optimizer.

## Правило

Нельзя считать capability доступной только потому, что платформа называется Codex, Claude Code или Antigravity.

В начале run optimizer должен определить фактические возможности среды.

## Базовые capabilities

```text
SESSION_USAGE_COUNTERS
SESSION_CONTEXT_TREE
LOCAL_TRANSCRIPTS
SKILL_DISCOVERY
MCP_DISCOVERY
TOOL_SCHEMA_DISCOVERY
PROJECT_INSTRUCTIONS_DISCOVERY
GLOBAL_INSTRUCTIONS_DISCOVERY
HOOK_DISCOVERY
SUBAGENT_USAGE
FRESH_CONTEXT
PROJECT_LOCAL_SKILL_INSTALL
EXTERNAL_CLI
ROLLBACK_SUPPORT
```

Каждая capability:

```text
SUPPORTED
PARTIAL
UNSUPPORTED
UNKNOWN
```

## Native Matreshka Context Telemetry

Основной runtime telemetry path — собственный engine:
- Codex: `SUPPORTED` для local rollout discovery/provider counters;
- Claude Code: `SUPPORTED/PARTIAL` для local JSONL usage; cross-file resume dedup пока отдельный hardening item;
- Antigravity: `PARTIAL` — безопасный static/statusline mode без live RPC/process probe.

Если native provider не может доказать counter semantics, capability остаётся `PARTIAL`/ `UNKNOWN`.

## CodeBurn

CodeBurn — optional compatibility/oracle capability, а не requirement. Если он уже установлен, его можно использовать для parity-check или дополнительного read-only evidence. Его отсутствие не деградирует native Codex telemetry.

## Codex

Проверять фактически:

- наличие local session data;
- доступность native Codex rollout parsing;
- provider-measured current-context semantics;
- skill directories;
- project/global scope;
- subagent/token usage counters.

## Claude Code

Проверять фактически:

- settings layers;
- MCP config;
- project/global skills;
- hooks;
- transcripts;
- native Claude JSONL parsing;
- optional CodeBurn oracle availability.

Нельзя переносить Claude-specific settings на другие harnesses.

## Antigravity / agy

Native Antigravity v0.2 намеренно избегает live language-server process probe/RPC и работает в safe partial mode. CodeBurn upstream может использоваться только как внешний референс/oracle для недостающих форматов.

Если runtime контекст нельзя измерить:

```text
MEASUREMENT = UNKNOWN
```

а не heuristic-as-fact.

## Graphify

Graphify — capability `REPOSITORY_GRAPH_NAVIGATION`.

Это отдельная внешняя capability, а не обязательная часть harness.

Adapter различает:

- `GRAPHIFY_CLI_AVAILABLE`;
- `GRAPHIFY_PROJECT_SKILL_INSTALLED`;
- `GRAPHIFY_GRAPH_READY`;
- `GRAPHIFY_GRAPH_POSSIBLY_STALE`;
- `GRAPHIFY_QUERY_READY`.

Project-scoped integration проверяется отдельно для Codex, Claude Code, Antigravity и generic Agent-Skills.

## Caveman

Caveman — capability `RECOVERABLE_CONTEXT_COMPRESSION`.

Не включать автоматически. Проверять:

- установка;
- совместимость;
- license/use boundary;
- реальная необходимость;
- approval.
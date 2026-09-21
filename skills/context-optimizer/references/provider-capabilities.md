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

## CodeBurn

CodeBurn рассматривается как основной telemetry adapter, если:

- установлен/доступен;
- provider поддерживается нужной командой;
- данные текущей среды действительно обнаружены.

Наличие CodeBurn не означает, что все команды дают одинаковую глубину по всем providers.

## Codex

Проверять фактически:

- наличие local session data;
- доступность CodeBurn provider parsing;
- context command support;
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
- CodeBurn optimize support.

Нельзя переносить Claude-specific settings на другие harnesses.

## Antigravity / agy

CodeBurn upstream содержит provider support для Antigravity, включая local-surface discovery, но optimizer обязан отдельно проверять, какие именно данные доступны в текущей установке.

Если runtime контекст нельзя измерить:

```text
MEASUREMENT = UNKNOWN
```

а не heuristic-as-fact.

## Graphify

Graphify — capability `REPOSITORY_GRAPH_NAVIGATION`.

Это отдельная внешняя capability, а не обязательная часть harness.

## Caveman

Caveman — capability `RECOVERABLE_CONTEXT_COMPRESSION`.

Не включать автоматически. Проверять:

- установка;
- совместимость;
- license/use boundary;
- реальная необходимость;
- approval.

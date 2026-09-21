# Оптимизатор контекста Matreshka

**Навык для анализа и оптимизации контекста AI-агентов: измерение расхода токенов, аудит skills и MCP, оптимизация инструкций и результатов инструментов, навигация по большим проектам, проверка эффективности изменений и интеграция с Matreshka Agent.**

Технический идентификатор навыка: `$context-optimizer`.

## Основная цель

Уменьшать ненужный context/token cost без ухудшения качества, точности, числа шагов и надёжности AI-агента.

## Базовый цикл

~~~text
MEASURE → DIAGNOSE → CLASSIFY → RECOMMEND
→ APPROVAL → APPLY → RE-MEASURE → VERIFY
→ KEEP / ROLLBACK
~~~

## Принципы

1. Сначала измерение, потом оптимизация.
2. Каждая цифра имеет provenance.
3. BYTE_COUNT и runtime tokens не смешиваются.
4. Read-only по умолчанию.
5. Reversible-first.
6. Меньше токенов не считается успехом при ухудшении качества.
7. Runtime telemetry по умолчанию собирается собственным `Matreshka Context Telemetry`; внешние инструменты не являются обязательным ядром.
8. Пользовательские инструкции и отчёты — на русском языке.

## Собственная runtime-телеметрия

Начиная с v0.2 основным источником runtime/session данных является **Matreshka Context Telemetry** — независимая реализация внутри этого репозитория.

- **Codex** — native discovery/parsing, provider token counters, current-context semantics, file/tool/skill/MCP events и byte-level context composition.
- **Claude Code** — native JSONL parsing с provider-measured usage; cross-file resume dedup пока считается ограничением.
- **Antigravity** — безопасный native SQLite mode + partial legacy PB: read-only `.db` decoding и optional existing-statusline parsing без live-process probe/RPC/hooks.

По умолчанию native telemetry не использует сеть, не сканирует процессы, не подключается к локальным RPC и не пишет session files. Cache выключен, пока явно не указан `--use-cache`.

## Внешние инструменты

- **CodeBurn** — больше не обязательная dependency. Оставлен как технический референс, optional compatibility layer и test oracle.
- **Caveman** — источник методологических принципов и optional future compression dependency; Engine внутрь проекта не копируется.
- **Graphify** — optional project-local repository navigation; внутрь проекта не копируется.
- **CShark-Hub/context-audit** — независимый методологический референс.

## Реализовано

- Gate 0–2: provenance, спецификация и machine-readable contracts;
- Gate 3: read-only static audit MVP;
- Gate 4: read-only CodeBurn compatibility adapter с сохранением `measured`/`estimated` provenance;
- Gate 5–11: собственные аудиторы, ingress, Graphify, reversible changes, ledger, Matreshka bridge и benchmark;
- Gate 12: native Matreshka Context Telemetry для Codex / Claude / безопасного Antigravity partial mode;
- smoke/eval suite для native telemetry, bridge, benchmark и compatibility paths.

В текущей версии **никакие настройки, MCP, skills или instruction files автоматически не изменяются**.

## Reversible optimization

Начиная с Gate 8 изменения могут применяться только как отдельные `CHG-xxx` с dry-run, exact approval, SHA-256 baseline, backup и hash-safe rollback. Сам факт finding не даёт права на mutation.

Optimization Ledger хранит отдельно события применения, отката и quality verification. `APPLIED` не считается `VERIFIED`.
## Benchmark и реальные пилоты

Gate 10 интегрирован с Matreshka Agent через compact bridge. Gate 11 содержит before/after evaluator и CI-пилот на реальном `matreshka-agent` checkout.

Runtime savings считаются подтверждёнными только по сопоставимым provider/tool-measured before/after сессиям без quality regression. Пока таких пар нет, verdict остаётся `UNVERIFIED` — static bytes и эвристики его не заменяют.

## Dependency policy

**CodeBurn не требуется для штатного измерения контекста.** Если он уже установлен, его можно использовать для parity-check во время разработки или как совместимый fallback. Context Optimizer не устанавливает CodeBurn автоматически.
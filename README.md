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
7. Внешние инструменты подключаются через адаптеры.
8. Пользовательские инструкции и отчёты — на русском языке.

## Внешние инструменты

- **CodeBurn** — runtime/session telemetry и findings. Реализован read-only adapter.
- **Caveman** — optional recoverable compression; Engine внутрь проекта не копируется.
- **Graphify** — optional project-local repository navigation; внутрь проекта не копируется.
- **CShark-Hub/context-audit** — независимый методологический референс.

## Реализовано

- Gate 0–2: provenance, спецификация и machine-readable contracts;
- Gate 3: read-only static audit MVP;
- Gate 4: read-only CodeBurn Adapter с сохранением `measured`/`estimated` provenance;
- smoke tests для static audit и CodeBurn normalization.

В текущей версии **никакие настройки, MCP, skills или instruction files автоматически не изменяются**.

Следующий этап — real-project pilot, расширение собственных аудиторов и Context Ingress Audit.
## Reversible optimization

Начиная с Gate 8 изменения могут применяться только как отдельные `CHG-xxx` с dry-run, exact approval, SHA-256 baseline, backup и hash-safe rollback. Сам факт finding не даёт права на mutation.

Optimization Ledger хранит отдельно события применения, отката и quality verification. `APPLIED` не считается `VERIFIED`.

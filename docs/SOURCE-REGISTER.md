# Реестр источников и provenance

Этот документ отделяет внешние источники от собственных решений проекта.

## Правила

Для каждого заимствованного решения указывать один из типов:

- `IDEA_ADAPTED` — взята идея, реализация собственная;
- `EXTERNAL_DEPENDENCY` — внешний инструмент используется как зависимость;
- `CODE_COPIED` — код скопирован с обязательным соблюдением лицензии и attribution;
- `INDEPENDENT_IMPLEMENTATION` — решение разработано независимо;
- `REFERENCE_ONLY` — материал использовался только для сравнения.

## SOURCE-001 — обучающий урок

**Тип:** `REFERENCE_ONLY + IDEA_ADAPTED`

Главные идеи:

- сначала измерить, затем оптимизировать;
- отдельно проверять MCP/connectors;
- отдельно проверять skills;
- контролировать размер project-memory/instruction files;
- уменьшать чрезмерный tool output;
- для больших репозиториев использовать структурную навигацию.

Числа из демонстрации автора не считаются универсальными метриками.

## SOURCE-002 — CodeBurn

Repository: https://github.com/getagentseal/codeburn

**Тип:** `EXTERNAL_DEPENDENCY + IDEA_ADAPTED`

Лицензия: MIT.

Используем:

- runtime/session measurement;
- context inspection;
- optimize findings;
- provider-specific telemetry;
- идеи re-measure и undo/report.

Не планируется форк или копирование CodeBurn целиком.

## SOURCE-003 — Caveman

Repository: https://github.com/JuliusBrussee/caveman

**Тип:** `OPTIONAL_EXTERNAL_DEPENDENCY + IDEA_ADAPTED`

Критично: репозиторий использует split licensing.

MIT-зоны включают adoption surfaces и skills; Engine-linked части, включая `engine/`, `proxy/`, `rewriter/`, `mcp/`, `shrink/` и другие указанные в upstream `LICENSING.md`, находятся под BSL-1.1.

Следствие для проекта:

- не копировать Caveman Engine;
- использовать внешний Caveman только как optional dependency;
- независимо реализовать собственную orchestration/safety логику;
- перенимать методологические идеи, а не закрытую реализацию.

## SOURCE-004 — Graphify

Repository: https://github.com/Graphify-Labs/graphify

**Тип:** `EXTERNAL_DEPENDENCY`

Текущая основная лицензия upstream: Apache-2.0; старые части могут сохранять MIT terms согласно upstream NOTICE.

Стратегия проекта:

- не копировать Graphify внутрь;
- хранить ссылку и инструкцию установки;
- предпочитать project-scoped install;
- сначала проверять, есть ли уже готовый graph;
- использовать graph-first navigation только когда это оправдано размером и поведением проекта.

## SOURCE-005 — CShark-Hub/context-audit

Repository: https://github.com/CShark-Hub/context-audit

**Тип:** `REFERENCE_ONLY + IDEA_ADAPTED`

Лицензия: MIT.

Полезные идеи:

- fail-closed при неизвестной schema;
- self-audit;
- `AUTO / DECIDE / MANUAL`;
- backup-before-write;
- поэлементное подтверждение;
- effective config view.

Не принимаем как источник истины эвристику `chars / 4` для runtime token usage.

## Собственное решение Matreshka Context Optimizer

**Тип:** `INDEPENDENT_IMPLEMENTATION`

Собственными остаются:

- measurement provenance model;
- cross-provider capability matrix;
- finding contract;
- optimization quality model;
- Optimization Ledger;
- Matreshka Agent bridge;
- dashboard semantics;
- acceptance/eval methodology.

# Интеграция с Matreshka Agent

## Граница ответственности

Matreshka Agent отвечает за orchestration разработки. Context Optimizer остаётся отдельным reusable skill/repository и передаёт только компактную проекцию состояния.

Context Optimizer отвечает за измерение, диагностику, рекомендации, reversible optimization и verification. Он не заменяет Project Intelligence, Router, task-local context envelopes, static Context Budget guardrails или authority model Matreshka.

## Критический invariant

**Static context bytes и runtime token usage — разные метрики.** Они никогда не складываются и не конвертируются друг в друга в bridge/dashboard.

## Канонический bridge

Bridge строится командой:

~~~bash
python skills/context-optimizer/scripts/matreshka_bridge.py \
  --audit audit.json \
  --runtime runtime.json \
  --graphify graphify.json \
  --ledger ledger-summary.json \
  --output context-optimizer-bridge.json
~~~

Machine-readable schema: `schemas/matreshka-bridge.schema.json`.

Ключевые поля:

~~~text
status
health + healthBasis
runtimeMeasurement.value/unit/type/source/semantics
staticContext.value(bytes)/fileCount
staticRisk
topFindings[]
recommendations[]
graphify.state
ledger.pendingVerification / rollbackRecommended
approvalRequired
source
~~~

## Truthfulness rules

- Текущий runtime context принимается только из доказанного current-context measurement.
- CodeBurn optimize `tokensSaved` не может стать runtime context count.
- Если runtime measurement отсутствует, bridge возвращает UNKNOWN; static bytes остаются отдельным полем.
- `health=UNKNOWN` не повышается до WARNING/OK по одной эвристике.
- `APPLIED` change без verification отображается как pending verification.
- Bridge — projection only и не даёт Matreshka права выполнять mutation.

## Dashboard

Matreshka может показывать:

- Runtime context — только exact/partial measured source;
- Static instructions — bytes;
- Context health и basis;
- top findings/recommendations;
- Graphify state;
- Optimization Ledger pending verification/rollback state.

Нельзя показывать static bytes как tokens или превращать рекомендацию optimizer в разрешение на изменение.

## Триггеры вызова

- `CONTEXT_TOO_BROAD`;
- runtime usage заметно растёт;
- повторные file/tool reads;
- oversized ingress;
- новый большой repository;
- много global skills/MCP;
- frequent compaction;
- перед длинным development run;
- после изменения AI tooling;
- после APPLY для обязательного re-measure/verify.

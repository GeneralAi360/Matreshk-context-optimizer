# Единый контракт Finding

## Назначение

Finding — минимальная проверяемая единица диагностики Context Optimizer.

Нельзя переходить от общего ощущения «контекст большой» сразу к изменению конфигурации.

## Обязательная цепочка

~~~text
PROBLEM
→ EVIDENCE
→ MEASUREMENT PROVENANCE
→ EXPECTED EFFECT
→ CONFIDENCE
→ QUALITY RISK
→ PROPOSAL
~~~

## Инварианты

1. Finding без evidence запрещён.
2. Finding без measurement provenance не может содержать точную цифру экономии.
3. `HEURISTIC_ESTIMATE` нельзя показывать как `PROVIDER_MEASURED`.
4. `BYTE_COUNT` нельзя автоматически переводить в runtime tokens.
5. `approval_required=false` в v0.1 допустим только для read-only действий.
6. В v0.1 findings имеют статус `OBSERVED`; apply-механизм ещё не включён.
7. External tool recommendation не равна разрешению на установку.

## Пример

~~~yaml
finding_id: CTX-001
category: INSTRUCTION_DUPLICATION
platform: generic
scope: PROJECT

problem:
  title: Повторяющаяся инструкция
  description: Одинаковое правило найдено в двух project instruction files.

evidence:
  - source: static-audit
    detail: Нормализованная строка совпадает в AGENTS.md и module/AGENTS.md.
    locator: AGENTS.md; module/AGENTS.md

measurement:
  value: 248
  unit: bytes
  measurement_type: BYTE_COUNT
  source: filesystem
  confidence: HIGH

expected_effect:
  direction: REDUCE_CONTEXT
  description: Удаление доказанного дубля уменьшит статический объём инструкций.
  estimated_saving: null

confidence: HIGH
quality_risk: MEDIUM

proposal:
  action: REVIEW_DUPLICATE_SCOPE
  description: Проверить, действительно ли правило должно существовать в обоих scopes.
  target: AGENTS.md

approval_required: true
status: OBSERVED
~~~

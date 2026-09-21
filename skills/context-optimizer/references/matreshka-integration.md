# Интеграция с Matreshka Agent

## Граница ответственности

Matreshka Agent отвечает за orchestration разработки.

Context Optimizer отвечает за:

- измерение контекстной нагрузки;
- диагностику потерь;
- рекомендации;
- verification оптимизаций.

Он не заменяет существующие:

- Project Intelligence;
- Context Budget guardrails;
- Router;
- task-local context envelopes;
- dashboard/ledger authority model.

## Важный invariant

Static context byte budgets Matreshka Agent и runtime token usage — разные метрики.

Никогда не объединять их в одно поле.

## Предлагаемый bridge

Matreshka получает компактный объект:

```yaml
context_optimizer:
  status: READY | DEGRADED | UNAVAILABLE
  health: OK | WARNING | CRITICAL | UNKNOWN

  runtime_measurement:
    value:
    unit:
    type:
    source:

  static_context:
    value:
    unit: bytes

  top_findings: []
  recommendations: []

  graphify:
    state: NOT_NEEDED | RECOMMENDED | INSTALLED | READY | STALE | UNKNOWN

  caveman:
    state: NOT_NEEDED | AVAILABLE | RECOMMENDED | ACTIVE | UNKNOWN

  approval_required: true | false
```

## Dashboard

Показывать раздельно:

- Runtime tokens;
- Static bytes;
- Estimated tokens;
- Unknown/unmeasurable;
- Context health;
- Active optimizer capabilities;
- Top recommendations.

Dashboard не даёт permission на mutation.

## Когда вызывать optimizer

Кандидатные триггеры:

- context становится TOO_BROAD;
- runtime usage резко растёт;
- много repeated reads;
- большой tool output;
- новый большой repository;
- много global skills/MCP;
- frequent compaction;
- перед длинным development run;
- после заметного изменения AI tooling.

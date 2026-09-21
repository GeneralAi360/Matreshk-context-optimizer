# Safety, approval и rollback model

## Режим по умолчанию

`READ_ONLY`.

Сам факт обнаружения проблемы не даёт права её исправлять.

## State machine

```text
FINDING
→ EVIDENCE
→ EXPECTED_EFFECT
→ QUALITY_RISK
→ PROPOSAL
→ DRY_RUN
→ APPROVAL
→ BACKUP
→ APPLY
→ RE_MEASURE
→ VERIFY
→ KEEP / ROLLBACK / UNVERIFIED
```

## Классы действий

### SAFE_READ

Только чтение/измерение.

Примеры:

- проверить установленные skills;
- прочитать конфигурацию;
- запустить read-only native telemetry;
- построить нативную карту проекта.

Не требует отдельного destructive approval.

### PROPOSE

Сформировать изменение без применения.

Примеры:

- предложить перенести skill из global в project scope;
- предложить вынести reference block;
- предложить отключить unused MCP.

### APPLY_REVERSIBLE

Изменение, для которого существует понятный backup/undo.

Требует подтверждения перед первым применением в v0.x.

### DESTRUCTIVE_OR_EXTERNAL

Примеры:

- удалить MCP;
- удалить skill;
- установить proxy/hook;
- менять глобальную конфигурацию;
- устанавливать внешний package;
- переписывать большой instruction file;
- удалять runtime cache.

Всегда требует явного approval.

## Запрет batch-mutation

В первой реализации изменения применяются по одному.

После каждого изменения:

1. validate;
2. re-measure;
3. verify quality;
4. сохранить ledger;
5. только затем переходить к следующему.

## Rollback

Перед изменением сохранять:

- target identity;
- previous content/config;
- timestamp;
- change id;
- hash, если применимо;
- undo procedure.

Если после изменения качество ухудшилось или ожидаемый эффект не подтверждён, статус не может быть PASS.

Допустимые решения:

- KEEP;
- ROLLBACK;
- UNVERIFIED;
- NEEDS_MORE_DATA.

## Fail-closed

Если optimizer не может доказать:

- текущую schema;
- target scope;
- source of truth;
- возможность безопасного rollback;

он обязан остановить конкретное изменение и продолжить только read-only анализ.
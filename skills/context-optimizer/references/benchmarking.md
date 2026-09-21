# Before/After Benchmarking

Gate 11 проверяет не «стало ли меньше токенов вообще», а причинную гипотезу: сопоставимая задача после конкретной оптимизации должна стоить дешевле без quality regression.

## Сопоставимость

До/после обязаны совпадать по:

- `task_id` и `task_class`;
- provider;
- model;
- token metric semantics;
- measurement type;
- measurement source/method.

Runtime acceptance использует только `PROVIDER_MEASURED` или сопоставимый `TOOL_MEASURED`. `HEURISTIC_ESTIMATE`, static bytes и tokenizer approximations дают `UNVERIFIED`.

## PASS

PASS разрешён только когда одновременно:

1. runtime token/context metric уменьшилась;
2. task success сохранён;
3. retries не выросли;
4. errors не выросли;
5. wrong-file reads не выросли;
6. information loss = `NO`.

Иначе сопоставимый run даёт FAIL. Недостаточная/несопоставимая evidence даёт UNVERIFIED.

## Команда

~~~bash
python evals/evaluate_before_after.py --before before.json --after after.json
~~~

Схемы: `benchmark-run.schema.json`, `benchmark-result.schema.json`.

## Real repository pilot

Отдельный pilot запускает read-only optimizer на реальном `matreshka-agent` package checkout и проверяет:

- target tree не изменился;
- package skills реально обнаружены;
- runtime tokens не выдуманы;
- static context остаётся bytes;
- Graphify status остаётся read-only;
- `.context-optimizer` state не создаётся read-only аудитом.

Такой pilot подтверждает интеграционную безопасность, но **не** доказывает runtime savings. Для runtime verdict нужны provider-measured before/after agent sessions.

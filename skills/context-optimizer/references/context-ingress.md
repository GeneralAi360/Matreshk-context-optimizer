# Context Ingress Audit

## Задача

Проверять не только то, что агент пишет, но и то, что попадает модели на вход через tool results, logs, JSON, diff и другие payload.

## Два режима

### 1. CodeBurn context tree

~~~bash
python skills/context-optimizer/scripts/analyze_context_tree.py --input context.json
~~~

Критично: в текущем CodeBurn block-level token counts в context tree являются оценками, а `reported.context` берётся из provider usage. Поэтому:

- `reported.context` → `PROVIDER_MEASURED`;
- block/effective/toolResult tokens → `HEURISTIC_ESTIMATE`;
- доля tool results может быть детерминированно рассчитана, но исходные counts всё равно estimated.

### 2. Отдельный payload

~~~bash
python skills/context-optimizer/scripts/analyze_payload.py --input tool-output.log
~~~

Payload analyzer не пытается угадывать токены. Он измеряет UTF-8 bytes, line count и повторяемость строк, определяет JSON/diff/log-like тип и создаёт только review findings.

## Safety

- Не обрезать tool output автоматически.
- Для logs/JSON/diff сохранять оригинал или recovery handle до будущего compression layer.
- Большой размер — review signal, не дефект.
- Дедупликация допустима только с сохранением счётчика повторов и оригинала.

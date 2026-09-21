# Context Ingress Audit

## Задача

Проверять не только ответы агента, но и данные, которые попадают модели на вход через tool results, logs, JSON, diff, directory listings и другие payload.

## Runtime-сигналы

Нативная telemetry фиксирует события чтения файлов, tools, MCP, skills и compaction там, где provider хранит эти данные.

Повторные чтения и большие tool results становятся review signal, но не автоматическим доказательством мусора.

## Отдельный payload

~~~bash
python skills/context-optimizer/scripts/analyze_payload.py --input tool-output.log
~~~

Payload analyzer не угадывает токены. Он измеряет UTF-8 bytes, line count и повторяемость строк, определяет JSON/diff/log-like форму и создаёт review findings.

## Правила

- Не обрезать tool output автоматически.
- Для logs/JSON/diff сохранять оригинал или recovery handle до компрессии.
- Большой размер — сигнал для проверки, не дефект сам по себе.
- Дедупликация допустима только с сохранением смысла, счётчика повторов и возможности восстановить исходные данные.
- Provider-measured runtime counters и byte-level ingress measurements остаются разными метриками.

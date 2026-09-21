# Политика автоматических запусков

Цель — запускать аудит тогда, когда он полезен, а не превращать сам optimizer в постоянный источник overhead.

## Триггеры

### NEW_PROJECT_BASELINE

`scenario=NEW_PROJECT` и baseline отсутствует → `start`. Запуск до массового fan-out задач.

### EXISTING_PROJECT_ADOPTION

`scenario=EXISTING_PROJECT` и baseline отсутствует → `adopt`. Запуск до изменения существующей архитектуры.

### RESUME_RECONCILIATION

Run возобновлён после паузы и baseline отсутствует либо последний аудит старше 24 часов → `resume`.

### PRESSURE_EVENT

`check` запускается, если есть минимум один подтверждённый сигнал:

- controller context = `CONTEXT_TOO_BROAD`;
- один и тот же файл прочитан 3+ раз;
- 2+ compaction в рабочей сессии;
- tool-result ratio >= 35% и объём tool results >= 64 КБ;
- static instructions выросли минимум на 16 КБ;
- изменился набор skills;
- изменилась MCP/tool-конфигурация;
- структура проекта изменилась минимум на 100 файлов.

Порог — сигнал на аудит, а не автоматический вывод «это мусор».

### MANUAL

Пользователь в любой момент может запросить `status`, `check` или `optimize`.

## Алгоритм

~~~text
Получить текущие сигналы
→ проверить сценарий проекта
→ проверить наличие baseline
→ проверить freshness
→ проверить pressure evidence
→ RUN / SKIP
→ записать причину в compact bridge
→ отобразить причину в dashboard
~~~

Детерминированный evaluator:

~~~bash
python skills/context-optimizer/scripts/trigger_policy.py --signal-json signal.json
~~~

## Защита от лишних запусков

Если нет нового evidence, возвращать `NO_TRIGGER`. Не запускать полный аудит на каждом сообщении, каждом tool call или каждом task transition.

После автоматического `check` не повторять тот же аудит, пока не изменился хотя бы один значимый сигнал или не началась новая задача с отдельным context envelope.

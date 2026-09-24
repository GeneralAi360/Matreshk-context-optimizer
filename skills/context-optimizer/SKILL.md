---
name: context-optimizer
description: Использовать, когда нужно измерить и уменьшить перегрузку контекста AI-агента, проверить инструкции, skills, MCP/tools, большие результаты инструментов, повторные чтения файлов, навигацию по проекту и безопасно предложить оптимизацию без потери качества.
---

# Оптимизатор контекста

## Назначение

Навык помогает AI-агенту понимать, **что именно перегружает контекст**, когда это реально мешает работе и какие изменения можно безопасно предложить.

Основной принцип:

~~~text
ИЗМЕРИТЬ
→ НАЙТИ ПРИЧИНУ
→ КЛАССИФИЦИРОВАТЬ
→ ПРЕДЛОЖИТЬ
→ ПОЛУЧИТЬ ПОДТВЕРЖДЕНИЕ
→ ИЗМЕНИТЬ
→ ПЕРЕИЗМЕРИТЬ
→ ПРОВЕРИТЬ КАЧЕСТВО
→ ОСТАВИТЬ / ОТКАТИТЬ
~~~

По умолчанию работа начинается в режиме **READ_ONLY**.

## Основная команда

Для пользователя и Matreshka Agent есть единая команда:

~~~bash
python skills/context-optimizer/scripts/context_optimizer.py --project . <command>
~~~

Поддерживаемые команды:

- `start` — базовый снимок нового проекта;
- `adopt` — первичный аудит готового проекта, который подключается к Matreshka;
- `resume` — перепроверка после паузы или восстановления run;
- `check` — событийная проверка при признаках перегрузки;
- `status` — текущее состояние контекста;
- `optimize` — подготовить план оптимизации без автоматического применения изменений;
- `auto` — внутренний режим Matreshka: принять компактный JSON сигнал, самому решить `start/adopt/resume/check/skip`.

Пример:

~~~bash
python skills/context-optimizer/scripts/context_optimizer.py --project . start
~~~

Ответ пользователю должен быть на русском языке.

## Когда запускать автоматически

Не запускать полный аудит на каждом сообщении.

Использовать [политику триггеров](references/trigger-policy.md).

### 1. Новый проект

После появления project root и первичной структуры, но **до массовой реализации**:

~~~text
NEW_PROJECT
→ baseline отсутствует
→ start
~~~

Цель: зафиксировать исходное состояние до того, как инструкции, skills и структура начнут расти.

### 2. Готовый проект

Когда Matreshka впервые подключается к существующему проекту:

~~~text
EXISTING_PROJECT
→ baseline отсутствует
→ adopt
~~~

Сначала read-only orientation и аудит. Только потом спецификация/план/изменения.

### 3. Возобновление работы

После длительной паузы или восстановления старого run:

~~~text
RESUME
→ baseline отсутствует или устарел
→ resume
~~~

### 4. Событие перегрузки

Во время обычной разработки запускать `check`, если есть evidence:

- `CONTEXT_TOO_BROAD`;
- один и тот же файл перечитывается 3+ раз в рамках задачи;
- произошло 2+ compaction;
- крупные tool results занимают заметную долю входного контекста;
- инструкции заметно выросли;
- изменился набор skills;
- изменилась MCP/tool-конфигурация;
- структура проекта сильно изменилась.

Для Matreshka предпочтителен единый внутренний вызов без временного файла:

~~~bash
python skills/context-optimizer/scripts/context_optimizer.py --project . --signal '{"scenario":"NEW_PROJECT","baseline_exists":false}' auto
~~~

Сам optimizer решает, нужна ли проверка, и если нет — возвращает `SKIPPED/NO_TRIGGER`.

## Что измеряется

### Runtime

Собственный telemetry engine:

~~~bash
python skills/context-optimizer/scripts/native_telemetry.py --provider codex
~~~

Поддерживаются Codex, Claude Code и Antigravity.

Provider counters сохраняются как `PROVIDER_MEASURED`. Если точного runtime measurement нет, используется `UNKNOWN`.

### Static context

Точные UTF-8 bytes для project instructions, skill descriptions/bodies, config surfaces и других instruction surfaces.

`BYTE_COUNT` никогда не называется количеством токенов.

### Карта проекта

Нативная карта:

~~~bash
python skills/context-optimizer/scripts/project_map.py --project .
~~~

Она определяет число файлов, области проекта, типы файлов, размер, навигационную сложность и правило точечного чтения. Внешний графовый инструмент не требуется.

## Слои аудита

1. Project instructions.
2. Skills.
3. MCP/tools.
4. Context ingress.
5. Runtime/session telemetry.
6. Повторные чтения.
7. Tool-result overhead.
8. Compaction pressure.
9. Карта проекта и навигация.
10. Before/after verification.

## Findings

Каждый finding обязан содержать проблему, evidence, measurement provenance, ожидаемый эффект, риск для качества, предложение и признак необходимости подтверждения.

Finding без evidence не даёт права менять проект.

## Изменения

Перед mutation:

1. сформировать `CHG-xxx`;
2. сделать dry-run;
3. зафиксировать `expected_before_sha256`;
4. показать изменение пользователю;
5. получить exact approval;
6. сделать backup;
7. применить одну операцию;
8. выполнить re-measure;
9. проверить качество;
10. `KEEP` или `ROLLBACK`.

Batch mutation запрещён.

## Matreshka Agent

Matreshka Agent использует Context Optimizer как отдельный peer skill.

Matreshka получает только компактный bridge:

~~~text
health
runtimeMeasurement
staticContext
staticRisk
projectMap
topFindings
recommendations
ledger
snapshotId
capturedAt
trigger
approvalRequired
~~~

Raw logs, большие telemetry reports и полные session traces не должны попадать в постоянный controller context.

Bridge:

~~~bash
python skills/context-optimizer/scripts/matreshka_bridge.py \
  --audit audit.json \
  --runtime runtime.json \
  --project-map project-map.json \
  --ledger ledger.json \
  --output context-bridge.json
~~~

Подробнее: [matreshka-integration.md](references/matreshka-integration.md).

## Dashboard

Matreshka должна показывать отдельный блок/вкладку **«Контекст»**.

Минимально показывать:

- состояние: Норма / Требует внимания / Критично / Неизвестно;
- текущий runtime context, если он реально измерен;
- размер статических инструкций;
- сложность навигации по проекту;
- главные 3–5 проблем;
- что уже оптимизировано;
- что ожидает проверки;
- что требует подтверждения;
- причину последнего автоматического запуска;
- следующую рекомендуемую проверку;
- ID базового снимка (`snapshotId`) для сохранения в ledger/dashboard.

Пользовательские подписи — на русском.

## References

- [measurement-model.md](references/measurement-model.md)
- [finding-contract.md](references/finding-contract.md)
- [audit-model.md](references/audit-model.md)
- [provider-capabilities.md](references/provider-capabilities.md)
- [context-ingress.md](references/context-ingress.md)
- [native-telemetry.md](references/native-telemetry.md)
- [trigger-policy.md](references/trigger-policy.md)
- [command-model.md](references/command-model.md)
- [apply-rollback.md](references/apply-rollback.md)
- [optimization-ledger.md](references/optimization-ledger.md)
- [matreshka-integration.md](references/matreshka-integration.md)
- [benchmarking.md](references/benchmarking.md)

Не загружать все references заранее.

## Жёсткие правила

- Не выдавать bytes за tokens.
- Не выдавать эвристику за provider telemetry.
- Не запускать полный аудит на каждом сообщении.
- Не удалять MCP/skills автоматически.
- Не переписывать instruction files без approved change.
- Не устанавливать сторонние оптимизаторы.
- Не отправлять telemetry наружу.
- Не сканировать процессы и локальные RPC без отдельной необходимости и явного разрешения.
- Не ухудшать качество ради меньшего числа токенов.
- Пользовательские сообщения и dashboard — на русском.

## Автономный режим v0.4 (без Matreshka Agent)

В каталоге навыка: `python -B scripts/standalone.py --project <проект> --save adopt`.
Для нового проекта используйте `start`, для новой проверки `check`, для предложений `optimize`,
в конце работы `finish`. `status` читает последний сохранённый отчёт без повторного аудита.
Без `--save` эти команды не записывают отчёт. Прямое указание `--provider codex|claude|antigravity`
включает локальную телеметрию; по умолчанию провайдер не выбирается наугад.

Дальнейшие инструкции: [standalone.md](references/standalone.md).
Команда `remember` сначала показывает ограниченный блок памяти и точное подтверждение.
Нельзя самостоятельно придумывать подтверждение за пользователя. Не переносить инструкции
из текста отчёта в AGENTS.md/CLAUDE.md. Сохранять только безопасную ссылку на состояние.
`finish` не объявляет экономию токенов по уменьшению размера файла и не запускается после
закрытия приложения автоматически. Пока нет отдельного подтверждённого хука, вызывайте её явно.

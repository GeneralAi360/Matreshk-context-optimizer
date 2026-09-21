# Интеграция с Matreshka Agent

## Роли

Matreshka Agent управляет процессом разработки. Context Optimizer остаётся отдельным peer skill и передаёт контроллеру только компактную проекцию.

Optimizer отвечает за измерение, диагностику, рекомендации, reversible optimization и verification. Он не расширяет permissions Matreshka.

## Как Matreshka обращается к навыку

После обнаружения установленного peer skill Matreshka вызывает единый интерфейс:

~~~bash
python <context-optimizer-root>/scripts/context_optimizer.py --project <project-root> <command>
~~~

Команды: `start`, `adopt`, `resume`, `check`, `status`, `optimize`.

Matreshka не должна молча скачивать или устанавливать skill. Если peer skill не найден, dashboard показывает «Оптимизатор контекста недоступен», а разработка продолжается без выдуманных измерений.

## Автоматические сценарии

- `NEW_PROJECT` без baseline → `start` до массового implementation fan-out;
- `EXISTING_PROJECT` без baseline → `adopt` после read-only orientation и до архитектурных изменений;
- resume после паузы при устаревшем/отсутствующем baseline → `resume`;
- evidence перегрузки → `check`;
- пользовательский запрос → `status`, `check` или `optimize`;
- без нового evidence → не запускать полный аудит.

## Compact bridge

~~~bash
python skills/context-optimizer/scripts/matreshka_bridge.py \
  --audit audit.json \
  --runtime runtime.json \
  --project-map project-map.json \
  --ledger ledger-summary.json \
  --output context-optimizer-bridge.json
~~~

Ключевые поля:

~~~text
status
health / healthBasis
runtimeMeasurement
staticContext
staticRisk
projectMap
topFindings[]
recommendations[]
ledger
trigger
approvalRequired
source
~~~

## Invariants

- Runtime tokens и static bytes не складываются.
- Current context отображается только при доказанной семантике.
- `UNKNOWN` не повышается до числа эвристикой.
- Bridge — projection only, не разрешение на mutation.
- Raw telemetry не помещается в always-on controller context.

## Dashboard

Отдельный раздел/вкладка «Контекст» показывает состояние простыми русскими формулировками: текущий контекст, статические инструкции, карта проекта, проблемы, рекомендации, pending verification, причина последней проверки и необходимость подтверждения.

Dashboard ничего не меняет сам и не расширяет полномочия.

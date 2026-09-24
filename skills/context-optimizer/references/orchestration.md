# Вызов из Matreshka Agent

Этот путь сохраняет совместимость с controller и не требует установки его копии в проект.
Автономные быстрые команды описаны отдельно в `installation.md` и `standalone.md`.

Matreshka обнаруживает источник peer skill и вызывает `scripts/context_optimizer.py` от его каталога,
передавая настоящий `--project`, provider и сигналы в `auto`. Этот entrypoint не переключается
на сохранение отчётов только потому, что появился `quick.py`.

```text
python -B <skill-root>/scripts/context_optimizer.py --project <project-root> --signal <JSON> auto
```

Пороговые правила принадлежат `trigger_policy.py`, не копируются во второй controller.
Новый проект без baseline, первое подключение готового проекта, возобновление и доказанная
перегрузка — разные сценарии; без новых оснований возвращается SKIPPED.

Matreshka получает compact bridge: snapshotId, capturedAt, health/healthBasis, runtimeMeasurement,
staticContext, projectMap, topFindings, recommendations, ledger, trigger и approvalRequired.
Сохраняет его своим контроллером только при наличии разрешения на запись состояния.
Raw transcripts, полные tool outputs и весь исторический журнал не загружаются автоматически.

Отсутствие установленного peer skill не расширяет полномочия: предложить локальную установку,
показать путь и предпросмотр, запросить подтверждение. Не скачивать и не исполнять код молча.
Наличие навыка не предоставляет сетевой доступ, право писать в Git или менять настройки host.

Оптимизация: измерение → evidence → предложение → отдельное согласие → изменение → повторное
измерение → проверка качества → оставить или откатить. Предложение и APPLIED не равны VERIFIED.
В текущем шаге автономный автоматический путь ограничен подтверждаемой записью памяти;
универсальный executor требует следующего прохода безопасности.

Подробные договоры: [интеграция](matreshka-integration.md), [триггеры](trigger-policy.md),
[измерения](measurement-model.md), [замечания](finding-contract.md), [подтверждения](approval-model.md),
[проверка эффекта](benchmarking.md). Загружать только нужный договор.

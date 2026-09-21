# SOURCE-004 — Graphify

Repository: https://github.com/Graphify-Labs/graphify

## Роль

Опциональная навигация по большим репозиториям и смешанным корпусам.

## Стратегия

Не копировать Graphify внутрь Matreshka Context Optimizer.

Использовать внешний project-scoped install, когда optimizer обнаружил реальную стоимость repository navigation.

Для Codex upstream поддерживает project-scoped установку, включая:

```bash
graphify install --project --platform codex
```

Если `graphify-out/graph.json` уже существует, предпочтителен graph-first fast path.

## Правило optimizer

```text
есть готовый graph?
  да → query graph → target files → read target files
  нет → доказать пользу → approval → install/build
```

## Лицензия

Текущий package metadata upstream указывает Apache-2.0; NOTICE также сообщает о частях, ранее распространявшихся под MIT.

## Provenance

`EXTERNAL_DEPENDENCY`.

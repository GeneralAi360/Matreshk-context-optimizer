# SOURCE-003 — Caveman

Repository: https://github.com/JuliusBrussee/caveman

## Полезные идеи

- `learn` перед изменениями;
- применять изменения по одному;
- re-measure;
- rollback, если улучшение не подтверждено;
- recoverable compression;
- оригиналы данных сохраняются отдельно.

## Лицензионная граница

Upstream использует split licensing.

MIT: skills и ряд adoption/SDK/CLI поверхностей.

BSL-1.1: Engine-linked части, включая указанные upstream `engine/`, `proxy/`, `rewriter/`, `mcp/`, `shrink/` и другие runtime-зоны.

## Решение проекта

- Caveman — optional external dependency;
- Engine не копируется;
- orchestration/safety/ledger реализуем сами;
- идеи адаптируем независимо.

## Provenance

`OPTIONAL_EXTERNAL_DEPENDENCY + IDEA_ADAPTED`.

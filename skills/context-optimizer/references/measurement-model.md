# Модель измерений

## Основное правило

Нельзя смешивать разные типы измерений и выдавать оценку за факт.

Каждое числовое значение обязано содержать provenance.

## Типы

### PROVIDER_MEASURED

Число получено из provider/runtime usage counters.

Пример:

```yaml
value: 18432
unit: tokens
measurement_type: PROVIDER_MEASURED
source: codeburn
provider: codex
```

Это предпочтительный источник runtime token usage.

### TOOL_MEASURED

Число измерено внешним инструментом, который имеет собственную методологию.

Требуется сохранить:

- tool name;
- version;
- method;
- raw source, если доступен.

### TOKENIZER_ESTIMATE

Текст пропущен через конкретный tokenizer или совместимый estimator.

Обязательно указать tokenizer/model assumption.

### BYTE_COUNT

Точный размер UTF-8/файла в байтах.

```yaml
value: 48291
unit: bytes
measurement_type: BYTE_COUNT
source: filesystem
```

BYTE_COUNT не является token count.

### HEURISTIC_ESTIMATE

Приближённая оценка, например chars / N.

Всегда маркировать как estimate и указывать формулу.

### UNKNOWN

Данных недостаточно.

UNKNOWN лучше ложной точности.

## Запрещённые преобразования

Нельзя:

- показывать static bytes Matreshka Agent как runtime tokens;
- складывать provider tokens и heuristic tokens в один "точный" total;
- считать размер файла доказательством того, что весь файл реально был загружен моделью;
- считать наличие MCP доказательством его точного runtime overhead без измерения;
- переносить token footprint из чужой системы как универсальное значение.

## Confidence

Каждый вывод должен иметь:

- HIGH — прямое измерение или воспроизводимое наблюдение;
- MEDIUM — несколько косвенных подтверждений;
- LOW — эвристика/гипотеза;
- UNKNOWN — нельзя оценить.

## Before/After

Сравнение допускается только при сопоставимых условиях:

- одинаковый provider/model или явно учтённое отличие;
- одинаковый/сопоставимый класс задач;
- известен baseline;
- измерения одного типа;
- нет скрытого изменения нескольких факторов одновременно, если цель — causal verification.

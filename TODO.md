# Актуальные задачи

Здесь остаются только незавершённые задачи, подтверждённые текущей
реализацией. Описание работающих memory-контуров находится в
[архитектуре Memory](docs/architecture/MEMORY.md).

## Semantic Memory

- Ввести каталог типизированных контекстов и применимость утверждения к
  проектам, группам и их сочетаниям. Сначала обеспечить явное разрешение
  `unknown` в review, затем перевести runtime с одиночного `project_id`.
- Перенести исторические `GlossaryMeaning` с проверенными источниками в
  semantic memory после ручной проверки применимости; определения без
  надёжного scope не публиковать автоматически.
- Завершить админскую проверку provenance: показывать claims, evaluations и
  конфликты в карточке знания; дать переход к исходному документу и запуск
  повторного extraction. API уже отдаёт большую часть этих данных, но экран
  карточки их пока не показывает.
- Проверить ACL для контента, aliases, relations, source counts и evidence на
  PostgreSQL с несколькими tenant. Добавить integration-тесты на повторную
  обработку checksum, снятие устаревших утверждений, rollback и конфликтующие
  claims.
- Проверить миграции `0135–0163` на копии production/shared-схемы и провести
  контролируемую обработку включённых документов.
- Уточнить и закрыть старую прямую публикацию документа из
  `runtime/memory/document_memory.py`: текущий ingest dispatch запускает shadow
  extraction со staging и review, а старый direct-publish worker остаётся в
  коде.
- Добавить эксплуатационные метрики extraction/review/publication и memory
  recall: принятые и отклонённые кандидаты, состояния знаний, конфликты,
  ошибки и решения об ACL-фильтрации.
- Проверить безопасное логирование extraction: уровни детализации, границы
  хранения prompt/document content и соответствие фонового trace настройкам.

## Runtime

- Удалить legacy operation-shaped контракты из LLM-потока там, где они ещё
  доступны; сохранить tool-first protocol и внутреннее разрешение операций.
- Добавить `QueryRewriter` за feature flag и сохранять исходный и
  переписанный запросы в runtime trace.
- Добавить remote enrichment для `collection.info` у SQL/API-коллекций:
  provider-aware profiling, freshness и безопасные distinct/top-value hints.

# Runtime Memory

Этот документ описывает memory-контекст, доступный во время выполнения
одного запроса. Полная карта persistence-контуров — в [Memory](MEMORY.md),
контекст одного чата — в [Chat Context Memory](CHAT_CONTEXT_MEMORY.md).

## Контекст одного запуска

`MemoryBuilder` создаёт bounded `MemorySnapshot` для запуска. В нём находятся
подтверждённые user/tenant facts и секции текущего turn: tool ledger,
результаты агентов, вложения и коллекции. `RuntimeTurnState` содержит
изменяемое состояние текущего запуска; он не заменяет сохраняемый план,
chat context или durable memory.

Диалоговые факты хранятся в `facts`; активны подтверждённые записи без
`superseded_by`. Их чтение и запись проходят через `MemoryService`/`FactStore`,
которые возвращают DTO и учитывают scope. После финального ответа chat
асинхронно запускает `FactExtractor -> FactCompactor -> FactReconciler`.
Сбой writeback не отменяет уже отправленный ответ.

## Semantic recall

Документные знания хранятся отдельно как source-backed `MemoryItem` и
`MemoryClaim`. Каноническая runtime operation — `memory.search`; она возвращает
bounded ACL-aware recall с терминами, подходящими знаниями, состояниями,
неопределённостью и источниками. В prompts не передаются ORM rows, ключи
хранилища или полный дамп памяти.

TurnPreflight начинает с механического поиска aliases/projects/entities без
чтения значений памяти. Для простого memory-grounded запроса он может запросить
ограниченный recall, после которого получает второй routing-вызов. Planner и
agents получают `memory.search` как инструмент и выбирают сведения по ходу
задачи. Memory не заменяет RAG для проверки основания и tools для получения
текущего состояния.

## Границы

- История сообщений передаётся runtime отдельно; `DialogueSummary` не является
  активным компонентом `MemoryBuilder`.
- Chat context сохраняет ссылки и рабочие указания одного чата, а не копии
  durable facts или документов.
- Sandbox overlays применяются только к снимку конкретного запуска.
- `runtime_execution_events` — журнал выполнения, не memory store.
- `WorkingMemory` и `ExecutionMemoryService` не являются текущим runtime
  контрактом.

# TODO

## Platform data integrity

### Project-memory lifecycle

- Реализовать source refresh, retention/cleanup и controlled removal для
  project facts через существующий
  `FactExtractor -> FactCompactor -> FactReconciler` flow.
- Добавить conflict detection и review/merge workflow для противоречащих
  project/process rules; active становится только approved revision.

## Runtime result representation

- Пересмотреть `summary_preview` и текущий лимит 800 символов: разделить
  внутренний результат задачи, bounded trace/progress summary и пользовательский
  ответ; сохранить лимит только там, где он служит конкретному bounded contract.

## Runtime terminology

- `iteration` — каноническая единица planner decision и её execution wave.
  Не вводить `PlanRevision` или patch как альтернативную модель runtime/UI.
- `planner_iteration` остаётся именем trace invocation; это не task и не
  отдельная версия плана.

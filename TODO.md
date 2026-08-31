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

## Planned breaking migration

- В отдельном breaking release переименовать legacy wire terminology
  `iteration`/`planner_iteration` в `PlanRevision` без смешения версии плана,
  визуального этапа и параллельной волны выполнения. До миграции projector
  продолжает отображать legacy rows как `plan_revision`.

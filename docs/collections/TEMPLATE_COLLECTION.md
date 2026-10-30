# Template collections

Template collections support only `.xlsx` and `.xlsm` files. A template is a
deterministic Excel layout, not a manually maintained web schema.

## Authoring a template

Put scalar anchors directly in cells: `{{company(name="Компания")}}`.

For a repeated table, keep the visible header row and put one technical marker
row below it. For example:

| Имя | Логин | Возраст |
| --- | --- | --- |
| `{{users[].name(name="Имя")}}` | `{{users[].login(name="Логин")}}` | `{{users[].age(name="Возраст")}}` |

The marker row is copied for each input item, so its styles and formulas are
preserved. An empty or absent optional list deletes that technical row. An
empty optional scalar removes just its anchor token. `required` is optional and
defaults to `false`.

## Lifecycle

1. Upload creates an `uploaded` row.
2. The deterministic parser reads anchors and derives `template_schema`.
3. The description is generated from the title and schema, then the row becomes
   `approval_required`.
4. In the status modal, a reviewer sees the schema read-only and may edit only
   the description. Saving keeps the status; approval is disabled until the
   edited description is saved.
5. Approval starts mandatory vectorization/indexing. Only then is the row
   `ready` and available to `collection.template.fill`.

The fill tool validates its `values` JSON against the stored contract, copies
the original template, writes a generated chat file through the artifact
writer, and returns `artifact_id`. The original template is downloaded through
the collection RBAC endpoint, not through a chat artifact identifier.

## Status modal presentation

The templates table combines the template name and a two-line description,
then shows status, version, and a compact structure summary. The structure
counts scalar fields outside tables, tables, and their columns; file format is
shown when available. Horizontal scrolling stays within the table region on
narrow screens.

The status modal keeps the existing seven-step pipeline and graph relationships.
Its graph has a bounded viewport: wide screens show all seven compact nodes when
space allows; narrow screens scroll only the graph row horizontally. The modal
body scrolls vertically, while the legend and selected-stage details stay outside
the graph scroller. Stage selection works by keyboard and is visually distinct
from the status color.

The detail panel gives each stage a short neutral explanation, then shows its
available timestamps and stage-specific information. If a stage has no start or
finish time, the panel uses one compact “Время не зафиксировано” message. The
description stage formats generated “Поля” and “Таблицы” sections as readable
lists; unrecognized description text remains visible with line wrapping. Known
template states and file formats are localized. The schema stage displays the
schema as a recursive, collapsible tree. Root objects and tables remain cards;
nested objects and scalar fields are peer rows within the parent tree. Field
names and descriptions stay on the left; data types and the required marker
align on the right. Internal schema keys and locator/source attributes are
omitted from the user view. Expanding a field reveals its examples and formats
when present.
Enum fields use the type label “Выбор из списка” and show up to six allowed
values as chips; longer lists reveal the remaining values through an “Ещё N”
disclosure. Enum chips sit beside the type and required marker on wide screens,
and wrap below them on narrow screens. Root table cards show their name, type,
and required marker; column counts, orientation, and row limits stay out of the
main view. The schema stage does not repeat the uploaded file's name, format,
or sheets.

Approval displays `approved_by_name` (the approver's full name, falling back to
login) when present. `approved_by` remains the raw audit identifier; it is
available on the displayed name's hover/focus and remains the source for audit
records. If the name is unavailable, the UI displays “Пользователь недоступен”
while preserving the identifier for audit inspection.

Vectorization counts describe vectors prepared for one embedding model;
indexing counts describe records across models. Therefore their totals can
differ. The modal labels those units separately and retains distinct counts when
the values in one stage do not match.

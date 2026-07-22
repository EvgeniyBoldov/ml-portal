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

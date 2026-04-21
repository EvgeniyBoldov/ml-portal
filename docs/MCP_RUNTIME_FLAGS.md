# MCP Runtime Flags Contract

Этот документ фиксирует runtime-контракт для metadata операций, публикуемых через MCP JSON Schema.

## JSON Schema Extension

Каждая operation может задать блок `x-runtime` внутри `inputSchema`:

```json
{
  "type": "object",
  "properties": {},
  "x-runtime": {
    "risk_level": "safe|write|destructive",
    "side_effects": false,
    "requires_confirmation": false,
    "credential_scope": "platform|user|auto"
  }
}
```

## Defaults

Если `x-runtime` отсутствует, применяются дефолты:

- `risk_level = "safe"`
- `side_effects = false`
- `requires_confirmation = false`
- `credential_scope = "auto"`

Если `x-runtime` задан частично, отсутствующие поля дополняются дефолтами.

## Validation Rules

В discovery-парсинге проверяются допустимые значения:

- `risk_level`: только `safe | write | destructive`
- `credential_scope`: только `platform | user | auto`
- `side_effects`: только boolean
- `requires_confirmation`: только boolean

Недопустимые значения приводят к `MCPDiscoveryValidationError` с указанием tool/operation, чтобы discovery fail-fast на некорректном контракте.

## Credential Resolution Semantics

`credential_scope = "auto"` означает, что стратегия выбора credentials определяется `CredentialScopeResolver` на основе:

- `risk_level`
- `side_effects`
- `requires_confirmation`

Явные значения `platform` и `user` имеют приоритет над автоматической стратегией.

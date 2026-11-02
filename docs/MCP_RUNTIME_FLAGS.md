# MCP Runtime Risk Contract

MCP servers do not control credential ownership or platform authorization. The platform assigns an effective risk classification to each discovered operation.

## Operation classification

The adapter policy must provide an explicit descriptor for every enabled operation:

```json
{
  "x-runtime": { "risk_level": "safe" }
}
```

The only accepted values are `safe` and `risky`. The adapter strips upstream `x-runtime` authority fields and emits only this locally configured risk value. It does not infer risk from tool names or MCP annotations. An enabled operation without a descriptor is a configuration error; an unclassified operation is not published for execution until an administrator assigns its risk in the platform.

The stored `discovered_tools.risk_level` is the platform's effective classification. MCP rescans do not overwrite an existing operator classification and do not delete inactive rows that have a classification. Legacy values are normalized during migration: `safe`, `read_only`, and `readonly` become `safe`; `write`, `mutable`, `mutating`, `destructive`, and `dangerous` become `risky`; unknown values become unclassified.

## Credential resolution

Credential ownership is derived only from the effective platform risk:

- `risky`: credentials owned by the requesting user only.
- `safe`: requesting user, then tenant, then platform credentials.

MCP-provided `credential_scope`, `side_effects`, and `requires_confirmation` do not select credential scope. A missing required credential leaves the operation visible; invocation returns a structured `credential_missing` result naming the operation, data instance, and required owner scope before sending an upstream request.

import type { AgentVersionCreate } from './agents';

export interface AgentVersionFormData extends AgentVersionCreate {
  task_contracts_json?: string;
}

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function toNullableStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const normalized = value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter((item) => item.length > 0);
  return normalized.length ? normalized : null;
}

export function parseTaskContracts(value: unknown): Record<string, unknown>[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(String(value ?? '[]'));
  } catch {
    throw new Error('Task contracts должны содержать корректный JSON');
  }

  if (
    !Array.isArray(parsed) ||
    parsed.some((item) => !item || typeof item !== 'object' || Array.isArray(item))
  ) {
    throw new Error('Task contracts должны быть JSON-массивом объектов');
  }
  return parsed as Record<string, unknown>[];
}

export function buildAgentVersionPayload(
  formData: Partial<AgentVersionFormData>,
  parentVersionId?: string,
): AgentVersionCreate {
  return {
    identity: toNullableString(formData.identity),
    mission: toNullableString(formData.mission),
    scope: toNullableString(formData.scope),
    planner_short_info: toNullableString(formData.planner_short_info),
    rules: toNullableString(formData.rules),
    tool_use_rules: toNullableString(formData.tool_use_rules),
    output_format: toNullableString(formData.output_format),
    examples: toNullableString(formData.examples),
    never_do: toNullableString(formData.never_do),
    allowed_ops: toNullableString(formData.allowed_ops),
    tags: toNullableStringArray(formData.tags),
    task_contracts: parseTaskContracts(formData.task_contracts_json),
    supports_dynamic_contracts: Boolean(formData.supports_dynamic_contracts),
    requires_fresh_retrieval: Boolean(formData.requires_fresh_retrieval),
    notes: toNullableString(formData.notes),
    parent_version_id: parentVersionId,
  };
}

import type { ResponseContract } from '@/shared/api/admin';

export interface ResponseContractCoverage {
  keys: string[];
  described: string[];
  missing: string[];
}

function normalize(text: string): string {
  return text.toLowerCase();
}

export function extractContractKeys(contract?: ResponseContract | null): string[] {
  if (!contract || contract.format !== 'json') return [];
  const props = contract.schema?.properties;
  if (!props || typeof props !== 'object' || Array.isArray(props)) return [];
  return Object.keys(props);
}

export function buildCoverage(
  contract: ResponseContract | null | undefined,
  rules: string | null | undefined,
  outputRequirements: string | null | undefined,
): ResponseContractCoverage {
  const keys = extractContractKeys(contract);
  if (keys.length === 0) {
    return { keys: [], described: [], missing: [] };
  }
  const combined = normalize(`${rules ?? ''}\n${outputRequirements ?? ''}`);
  const described = keys.filter((key) => combined.includes(normalize(key)));
  const describedSet = new Set(described);
  const missing = keys.filter((key) => !describedSet.has(key));
  return { keys, described, missing };
}


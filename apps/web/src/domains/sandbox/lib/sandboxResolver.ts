import type { SandboxBranchOverride } from '../types';

export interface ResolverFieldState {
  field_path: string;
  base_value: unknown;
  override_value: unknown;
  effective_value: unknown;
  is_overridden: boolean;
}

export class SandboxResolver {
  private readonly overrideMap: Map<string, SandboxBranchOverride>;

  constructor(overrides: SandboxBranchOverride[]) {
    this.overrideMap = new Map(
      overrides.map((item) => [
        this.key(item.entity_type, item.entity_id, item.field_path),
        item,
      ]),
    );
  }

  private key(entityType: string, entityId: string | null, fieldPath: string): string {
    return `${entityType}:${entityId ?? ''}:${fieldPath}`;
  }

  getOverride(
    entityType: string,
    entityId: string | null,
    fieldPath: string,
  ): SandboxBranchOverride | undefined {
    return this.overrideMap.get(this.key(entityType, entityId, fieldPath));
  }

  hasFieldOverride(entityType: string, entityId: string | null, fieldPath: string): boolean {
    return this.overrideMap.has(this.key(entityType, entityId, fieldPath));
  }

  hasEntityOverrides(entityType: string, entityId: string | null): boolean {
    const prefix = `${entityType}:${entityId ?? ''}:`;
    for (const key of this.overrideMap.keys()) {
      if (key.startsWith(prefix)) {
        return true;
      }
    }
    return false;
  }

  resolveField(
    entityType: string,
    entityId: string | null,
    fieldPath: string,
    baseValue: unknown,
  ): ResolverFieldState {
    const override = this.getOverride(entityType, entityId, fieldPath);
    const hasOverride = Boolean(override);
    const overrideValue = override?.value_json;
    return {
      field_path: fieldPath,
      base_value: baseValue,
      override_value: overrideValue,
      effective_value: hasOverride ? overrideValue : baseValue,
      is_overridden: hasOverride,
    };
  }
}


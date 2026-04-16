import type { RbacEffect, RbacLevel, ResourceType } from '@/shared/api/rbac';

export const RBAC_LEVEL_LABELS: Record<RbacLevel, string> = {
  platform: 'Платформа',
  tenant: 'Тенант',
  user: 'Пользователь',
};

export const RBAC_LEVEL_TONES: Record<RbacLevel, 'info' | 'warn' | 'neutral'> = {
  platform: 'info',
  tenant: 'warn',
  user: 'neutral',
};

export const RBAC_EFFECT_LABELS: Record<RbacEffect, string> = {
  allow: 'Разрешён',
  deny: 'Запрещён',
};

export const RBAC_EFFECT_TONES: Record<RbacEffect, 'success' | 'danger'> = {
  allow: 'success',
  deny: 'danger',
};

export const RBAC_RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  agent: 'Агент',
  tool: 'Инструмент',
  instance: 'Коннектор',
};

export const RBAC_RESOURCE_TYPE_ORDER: Record<ResourceType, number> = {
  agent: 0,
  tool: 1,
  instance: 2,
};

function isLikelyUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value.trim());
}

export function formatRbacOwnerLabel(level: RbacLevel, name?: string | null): string {
  const normalized = name?.trim();
  if (!normalized || isLikelyUuid(normalized)) {
    return RBAC_LEVEL_LABELS[level];
  }
  return normalized;
}

export function formatRbacResourceLabel(type: ResourceType, name?: string | null): string {
  const normalized = name?.trim();
  if (!normalized || isLikelyUuid(normalized)) {
    return RBAC_RESOURCE_TYPE_LABELS[type];
  }
  return normalized;
}

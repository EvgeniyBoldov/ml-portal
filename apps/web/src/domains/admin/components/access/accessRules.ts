import {
  rbacApi,
  type EnrichedRule,
  type RbacLevel,
  type ResourceType,
} from '@/shared/api/rbac';
import {
  RBAC_LEVEL_LABELS,
  RBAC_RESOURCE_TYPE_LABELS,
} from '@/domains/admin/shared/rbacLabels';

export const ACCESS_PATH = '/admin/access';
export const accessBreadcrumb = { label: 'Права доступа', href: ACCESS_PATH };

export const ownerOptions = [
  { value: 'platform', label: 'Вся платформа' },
  { value: 'tenant', label: 'Рабочая группа' },
  { value: 'user', label: 'Пользователь' },
] satisfies { value: RbacLevel; label: string }[];

export const resourceOptions = [
  { value: 'agent', label: 'Агент' },
  { value: 'instance', label: 'Коллекция' },
] satisfies { value: ResourceType; label: string }[];

export const decisionOptions = [
  { value: 'allow', label: 'Разрешить доступ' },
  { value: 'deny', label: 'Запретить доступ' },
];

export function resourceTypeName(type: string) {
  const labels: Record<string, string> = {
    ...RBAC_RESOURCE_TYPE_LABELS,
    instance: 'Данные',
    collection: 'Коллекция',
    operation: 'Операция',
  };
  return labels[type] ?? 'Ресурс';
}

export function ownerName(owner: EnrichedRule['owner']) {
  return owner.platform
    ? 'Вся платформа'
    : owner.name || RBAC_LEVEL_LABELS[owner.level];
}

export function statusName(rule: EnrichedRule) {
  return rule.lifecycle_status === 'deprecated' ? 'К удалению' : 'Действует';
}

export function isEditable(type: ResourceType) {
  return type === 'agent' || type === 'instance';
}

export async function loadAccessRules() {
  const limit = 500;
  const rules: EnrichedRule[] = [];
  for (let skip = 0; ; skip += limit) {
    const page = await rbacApi.listEnrichedRules({
      include_deprecated: true,
      limit,
      skip,
    });
    rules.push(...page);
    if (page.length < limit) return rules;
  }
}

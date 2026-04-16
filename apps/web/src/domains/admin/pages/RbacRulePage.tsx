/**
 * RbacRulePage — read/edit view with inheritance chain.
 *
 * Shows the selected rule in context:
 * default -> platform -> tenant -> user
 * and renders only human-readable names in the UI.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@/shared/api/admin';
import { rbacApi, type RbacEffect } from '@/shared/api/rbac';
import { qk } from '@/shared/api/keys';
import { useRbacRuleEditor } from '@/shared/hooks/useRbacRuleEditor';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui/EntityPage';
import { Block } from '@/shared/ui/GridLayout';
import { Badge, Button, ConfirmDialog } from '@/shared/ui';
import {
  RBAC_EFFECT_LABELS,
  RBAC_EFFECT_TONES,
  RBAC_LEVEL_LABELS,
  RBAC_LEVEL_TONES,
  RBAC_RESOURCE_TYPE_LABELS,
  formatRbacOwnerLabel,
  formatRbacResourceLabel,
} from '../shared/rbacLabels';

type InheritanceLayerKey = 'default' | 'platform' | 'tenant' | 'user';

interface InheritanceLayer {
  key: InheritanceLayerKey;
  title: string;
  ownerLabel: string;
  ownerMeta?: string | null;
  explicitEffect: RbacEffect | null;
  effectiveEffect: RbacEffect;
  current: boolean;
  note: string;
  sourceLabel: string;
}

function effectBadge(effect: RbacEffect | null) {
  if (!effect) {
    return <Badge tone="neutral">Не определён</Badge>;
  }
  return <Badge tone={RBAC_EFFECT_TONES[effect]}>{RBAC_EFFECT_LABELS[effect]}</Badge>;
}

function layerTone(layerKey: InheritanceLayerKey) {
  if (layerKey === 'default') return 'neutral' as const;
  if (layerKey === 'platform') return 'info' as const;
  if (layerKey === 'tenant') return 'warn' as const;
  return 'success' as const;
}

export function RbacRulePage() {
  const {
    id,
    rule,
    isLoading,
    mode,
    effect,
    setEffect,
    saving,
    showDeleteConfirm,
    setShowDeleteConfirm,
    handleEdit,
    handleSave,
    handleCancel,
    handleDelete,
    handleDeleteConfirm,
  } = useRbacRuleEditor();

  const resourceType = rule?.resource_type;
  const resourceId = rule?.resource_id ?? null;

  const { data: resourceRules = [] } = useQuery({
    queryKey: qk.rbac.enrichedRules({ resource_type: resourceType, resource_id: resourceId ?? undefined }),
    queryFn: () => rbacApi.listEnrichedRules({
      resource_type: resourceType ?? undefined,
      resource_id: resourceId ?? undefined,
    }),
    enabled: !!resourceType && !!resourceId,
    staleTime: 30_000,
  });

  const currentRule = useMemo(
    () => resourceRules.find((r) => r.id === id) ?? null,
    [resourceRules, id],
  );

  const ruleOwner = currentRule?.owner ?? null;
  const ownerUserId = rule?.owner_user_id ?? currentRule?.owner?.user_id ?? null;
  const ownerTenantId = rule?.owner_tenant_id ?? currentRule?.owner?.tenant_id ?? null;

  const { data: ownerUser } = useQuery({
    queryKey: ownerUserId ? qk.admin.users.detail(ownerUserId) : ['admin', 'users', 'undefined'],
    queryFn: () => adminApi.getUser(ownerUserId!),
    enabled: !!ownerUserId,
    staleTime: 30_000,
  });

  const effectiveTenantId = ownerTenantId ?? ownerUser?.tenant_id ?? null;

  const { data: ownerTenant } = useQuery({
    queryKey: effectiveTenantId ? qk.admin.tenants.detail(effectiveTenantId) : ['admin', 'tenants', 'undefined'],
    queryFn: () => adminApi.getTenant(effectiveTenantId!),
    enabled: !!effectiveTenantId,
    staleTime: 30_000,
  });

  const platformRule = useMemo(
    () => resourceRules.find((r) => r?.owner?.platform) ?? null,
    [resourceRules],
  );

  const tenantRule = useMemo(
    () => (effectiveTenantId
      ? resourceRules.find((r) => r?.owner?.tenant_id === effectiveTenantId) ?? null
      : null),
    [resourceRules, effectiveTenantId],
  );

  const userRule = useMemo(
    () => (ownerUserId
      ? resourceRules.find((r) => r?.owner?.user_id === ownerUserId) ?? null
      : null),
    [resourceRules, ownerUserId],
  );

  const ownerLabel = useMemo(() => {
    if (!rule && !currentRule) return '';
    if (ruleOwner?.platform) return 'Платформа';
    if (ruleOwner?.user_id) return ownerUser?.login || ruleOwner.name;
    if (ruleOwner?.tenant_id) return ownerTenant?.name || ruleOwner.name;
    return ruleOwner?.name || '—';
  }, [rule, currentRule, ownerTenant?.name, ownerUser?.login, ruleOwner]);

  const ownerMeta = useMemo(() => {
    if (!rule && !currentRule) return null;
    if (ruleOwner?.user_id && ownerTenant?.name) {
      return `Тенант: ${ownerTenant.name}`;
    }
    return null;
  }, [rule, currentRule, ownerTenant?.name, ruleOwner?.user_id]);

  const layers = useMemo<InheritanceLayer[]>(() => {
    if (!rule && !currentRule) return [];

    const result: InheritanceLayer[] = [];
    let effective: RbacEffect = 'deny';

    result.push({
      key: 'default',
      title: 'Дефолт системы',
      ownerLabel: 'Системный дефолт',
      explicitEffect: null,
      effectiveEffect: effective,
      current: false,
      note: 'Базовый fallback: если на слоях выше нет явного правила, доступ закрыт.',
      sourceLabel: 'System',
    });

    const platformEffective = platformRule?.effect ?? effective;
      result.push({
        key: 'platform',
        title: 'Платформа',
        ownerLabel: 'Платформа',
        explicitEffect: platformRule?.effect ?? null,
        effectiveEffect: platformEffective,
        current: !!ruleOwner?.platform,
        note: platformRule
          ? 'Есть явное правило на платформе.'
          : 'Явного платформенного правила нет, наследуется дефолт.',
        sourceLabel: platformRule ? 'explicit' : 'inherited',
      });

    effective = platformEffective;

    if (effectiveTenantId) {
      const tenantEffective = tenantRule?.effect ?? effective;
        result.push({
          key: 'tenant',
          title: ownerTenant?.name ? `Тенант: ${ownerTenant.name}` : 'Тенант',
          ownerLabel: ownerTenant?.name || 'Тенант',
          ownerMeta: ownerTenant?.description ?? null,
          explicitEffect: tenantRule?.effect ?? null,
          effectiveEffect: tenantEffective,
          current: !!ruleOwner?.tenant_id,
          note: tenantRule
            ? 'Есть явное правило на тенанте.'
            : 'Явного тенантного правила нет, наследуется с платформы.',
          sourceLabel: tenantRule ? 'explicit' : 'inherited',
        });
      effective = tenantEffective;
    }

    if (ownerUserId) {
      const userEffective = userRule?.effect ?? effective;
        result.push({
          key: 'user',
          title: ownerUser?.login ? `Пользователь: ${ownerUser.login}` : 'Пользователь',
          ownerLabel: ownerUser?.login || 'Пользователь',
          ownerMeta: ownerTenant?.name ? `Тенант: ${ownerTenant.name}` : null,
          explicitEffect: userRule?.effect ?? null,
          effectiveEffect: userEffective,
          current: !!ruleOwner?.user_id,
          note: userRule
            ? 'Есть явное правило на пользователе.'
            : 'Явного пользовательского правила нет, наследуется от тенанта.',
          sourceLabel: userRule ? 'explicit' : 'inherited',
        });
    }

    return result;
  }, [rule, platformRule, tenantRule, userRule, effectiveTenantId, ownerTenant?.description, ownerTenant?.name, ownerUser?.login, ownerUserId]);

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'RBAC', href: '/admin/rbac' },
    { label: 'Правило' },
  ];

  const currentResourceName = currentRule
    ? formatRbacResourceLabel(
        currentRule.resource.type,
        currentRule.resource.name || currentRule.resource.slug || undefined,
      )
    : '';

  return (
    <>
      <EntityPageV2
        title="RBAC правило"
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/rbac"
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
        actionButtons={
          mode === 'view' ? (
            <Button variant="danger" onClick={handleDelete}>Удалить</Button>
          ) : undefined
        }
      >
        <Tab title="Обзор" layout="grid">
          <Block
            title="Контекст"
            icon="user"
            iconVariant="info"
            width="1/2"
            headerActions={rule ? <Badge tone={RBAC_LEVEL_TONES[rule.level]}>{RBAC_LEVEL_LABELS[rule.level]}</Badge> : undefined}
          >
            <div style={{ display: 'grid', gap: 12 }}>
              <div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Владелец</div>
                <div style={{ fontWeight: 500 }}>{ownerLabel || '—'}</div>
                {ownerMeta && (
                  <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 2 }}>{ownerMeta}</div>
                )}
              </div>
              <div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Создано</div>
                <div>{rule?.created_at ? new Date(rule.created_at).toLocaleString('ru-RU') : '—'}</div>
              </div>
              <div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Создал</div>
                <div style={{ fontWeight: 500 }}>{currentRule?.created_by_name || '—'}</div>
              </div>
            </div>
          </Block>

          <Block
            title="Ресурс"
            icon="shield"
            iconVariant="primary"
            width="1/2"
            headerActions={currentRule ? <Badge tone={RBAC_EFFECT_TONES[currentRule.effect]}>{RBAC_EFFECT_LABELS[currentRule.effect]}</Badge> : undefined}
          >
            <div style={{ display: 'grid', gap: 12 }}>
              <div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Тип ресурса</div>
                <div style={{ fontWeight: 500 }}>
                  {currentRule ? RBAC_RESOURCE_TYPE_LABELS[currentRule.resource.type] : '—'}
                </div>
              </div>
              <div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Ресурс</div>
                <div style={{ fontWeight: 500 }}>
                  {currentResourceName || currentRule?.resource.name || currentRule?.resource.slug || '—'}
                </div>
              </div>
              <div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Текущее действие</div>
                {currentRule ? effectBadge(currentRule.effect) : <Badge tone="neutral">—</Badge>}
              </div>
            </div>
          </Block>
        </Tab>

        <Tab title="Наследование" layout="full">
          <div style={{ display: 'grid', gap: 16 }}>
            {layers.map((layer) => (
              <Block
                key={layer.key}
                title={layer.title}
                icon="layers"
                iconVariant={layer.current ? 'success' : layer.key === 'default' ? 'neutral' : 'info'}
                width="full"
                headerActions={
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <Badge tone={layerTone(layer.key)}>
                      {layer.current ? 'Текущий слой' : layer.sourceLabel === 'explicit' ? 'Явное правило' : 'Наследование'}
                    </Badge>
                    {effectBadge(layer.explicitEffect)}
                  </div>
                }
              >
                <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: 12 }}>
                  <div>
                    <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Владелец</div>
                    <div style={{ fontWeight: 500 }}>{layer.ownerLabel}</div>
                    {layer.ownerMeta && (
                      <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 2 }}>{layer.ownerMeta}</div>
                    )}
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Явный эффект</div>
                    {effectBadge(layer.explicitEffect)}
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Эффективно</div>
                    <Badge tone={RBAC_EFFECT_TONES[layer.effectiveEffect]}>{RBAC_EFFECT_LABELS[layer.effectiveEffect]}</Badge>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>Пояснение</div>
                    <div style={{ color: 'var(--text-secondary)' }}>{layer.note}</div>
                  </div>
                </div>
              </Block>
            ))}
          </div>
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить RBAC правило?"
        message="Это действие необратимо. Правило будет удалено навсегда."
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

export default RbacRulePage;

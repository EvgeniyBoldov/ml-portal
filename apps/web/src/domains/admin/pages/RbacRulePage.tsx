/**
 * RbacRulePage - Просмотр/редактирование RBAC правила (EntityPageV2)
 */
import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  rbacApi, 
  type RbacRuleUpdate, 
  type RbacEffect, 
  type ResourceType, 
  type RbacLevel 
} from '@/shared/api/rbac';
import { agentsApi } from '@/shared/api/agents';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  EntityPageV2,
  Tab,
  type EntityPageMode,
} from '@/shared/ui/EntityPage/EntityPageV2';
import {
  ContentBlock,
  Badge,
  Input,
  Button,
} from '@/shared/ui';
import styles from './RbacRulePage.module.css';

interface FormData {
  level: RbacLevel;
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  agent: 'Агент',
  toolgroup: 'Группа инструментов',
  tool: 'Инструмент',
  instance: 'Инстанс',
};

const EFFECT_LABELS: Record<string, { label: string; tone: 'success' | 'danger' }> = {
  allow: { label: 'Разрешён', tone: 'success' },
  deny: { label: 'Запрещён', tone: 'danger' },
};

export function RbacRulePage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit';

  const [formData, setFormData] = useState<FormData>({
    level: 'platform',
    resource_type: 'agent',
    resource_id: '',
    effect: 'deny',
  });
  const [saving, setSaving] = useState(false);

  // ─── Queries ─────────────────────────────────────────────────────

  const { data: rule, isLoading } = useQuery({
    queryKey: qk.rbac.detail(id!),
    queryFn: () => rbacApi.getRule(id!),
    enabled: !!id,
  });

  // Load agents for resource name resolution
  const { data: agents = [] } = useQuery({
    queryKey: qk.agents.list({}),
    queryFn: () => agentsApi.list(),
  });

  // Load tool groups
  const { data: toolGroups = [] } = useQuery({
    queryKey: qk.toolGroups.list({}),
    queryFn: async () => {
      const { apiRequest } = await import('@/shared/api/http');
      return apiRequest('/admin/tool-groups') as Promise<any[]>;
    },
  });

  // ─── Sync form ─────────────────────────────────────────────────────

  useEffect(() => {
    if (rule) {
      setFormData({
        level: rule.level,
        resource_type: rule.resource_type,
        resource_id: rule.resource_id,
        effect: rule.effect,
      });
    }
  }, [rule]);

  // ─── Mutations ─────────────────────────────────────────────────────

  const updateMutation = useMutation({
    mutationFn: (data: RbacRuleUpdate) => rbacApi.updateRule(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.detail(id!) });
      queryClient.invalidateQueries({ queryKey: qk.rbac.list({}) });
      showSuccess('RBAC правило обновлено');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ──────────────────────────────────────────────────────

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMutation.mutateAsync({
        effect: formData.effect,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (rule) {
      setFormData({
        level: rule.level,
        resource_type: rule.resource_type,
        resource_id: rule.resource_id,
        effect: rule.effect,
      });
    }
    setSearchParams({});
  };

  // ─── Resource name resolver ────────────────────────────────────────

  const getResourceName = (resourceType: string, resourceId: string): string => {
    if (resourceType === 'agent') {
      const agent = agents.find((a: any) => a.id === resourceId);
      return agent ? `${agent.name} (${agent.slug})` : resourceId.slice(0, 8) + '...';
    }
    if (resourceType === 'toolgroup') {
      const group = toolGroups.find((g: any) => g.id === resourceId);
      return group ? `${group.name} (${group.slug})` : resourceId.slice(0, 8) + '...';
    }
    return resourceId.slice(0, 8) + '...';
  };

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <EntityPageV2
      title="RBAC правило"
      mode={mode}
      loading={isLoading}
      saving={saving}
    >
      <Tab 
        title="Обзор" 
        layout="single"
        actions={
          mode === 'view' ? [
            <Button key="edit" variant="primary" onClick={() => setSearchParams({ mode: 'edit' })}>
              Редактировать
            </Button>,
          ] : mode === 'edit' ? [
            <Button key="save" variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : undefined
        }
      >
        {/* Rule info */}
        <ContentBlock title="Информация о правиле" icon="settings">
          <div className={styles['form-grid']}>
            <div className={styles['form-field']}>
              <label className={styles.label}>ID правила</label>
              <Input value={rule?.id || ''} disabled />
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>Уровень</label>
              <div className={styles['badge-row']}>
                <Badge tone="neutral">{rule?.level || ''}</Badge>
              </div>
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>Тип ресурса</label>
              <Input value={RESOURCE_TYPE_LABELS[rule?.resource_type || ''] || rule?.resource_type || ''} disabled={!isEditable} />
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>Ресурс</label>
              <Input value={rule ? getResourceName(rule.resource_type, rule.resource_id) : ''} disabled={!isEditable} />
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>Эффект</label>
              {isEditable ? (
                <select
                  className={styles.select}
                  value={formData.effect}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, effect: e.target.value as RbacEffect }))
                  }
                >
                  <option value="deny">Запрещён</option>
                  <option value="allow">Разрешён</option>
                </select>
              ) : (
                <div className={styles['badge-row']}>
                  <Badge tone={EFFECT_LABELS[rule?.effect || 'deny'].tone}>
                    {EFFECT_LABELS[rule?.effect || 'deny'].label}
                  </Badge>
                </div>
              )}
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>Создан</label>
              <Input value={rule ? new Date(rule.created_at).toLocaleString('ru-RU') : ''} disabled />
            </div>
          </div>
        </ContentBlock>
      </Tab>
    </EntityPageV2>
  );
}

export default RbacRulePage;

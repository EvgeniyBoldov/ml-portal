/**
 * RbacRuleCreatePage - Создание RBAC правила для владельца (EntityPageV2)
 */
import { useState, useMemo, type ChangeEvent } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  rbacApi, 
  type RbacRuleCreate, 
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
} from '@/shared/ui/EntityPage/EntityPageV2';
import {
  ContentBlock,
  Badge,
  Input,
  Button,
} from '@/shared/ui';
import styles from './RbacRuleCreatePage.module.css';

interface FormData {
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
}

export function RbacRuleCreatePage() {
  const location = useLocation();
  const { id: ownerId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [formData, setFormData] = useState<FormData>({
    resource_type: 'agent',
    resource_id: '',
    effect: 'deny',
  });
  const [saving, setSaving] = useState(false);

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

  // ─── Determine owner info ───────────────────────────────────────────

  const ownerInfo = useMemo(() => {
    if (location.pathname.startsWith('/admin/users/')) {
      if (!ownerId) {
        throw new Error('Invalid user owner id');
      }
      return {
        level: 'user' as RbacLevel,
        owner_user_id: ownerId,
        owner_tenant_id: null,
        owner_platform: false,
        title: 'Пользователь',
        backPath: `/admin/users/${ownerId}`,
      };
    }
    if (location.pathname.startsWith('/admin/tenants/')) {
      if (!ownerId) {
        throw new Error('Invalid tenant owner id');
      }
      return {
        level: 'tenant' as RbacLevel,
        owner_user_id: null,
        owner_tenant_id: ownerId,
        owner_platform: false,
        title: 'Тенант',
        backPath: `/admin/tenants/${ownerId}`,
      };
    }
    if (location.pathname.startsWith('/admin/platform/')) {
      return {
        level: 'platform' as RbacLevel,
        owner_user_id: null,
        owner_tenant_id: null,
        owner_platform: true,
        title: 'Платформа',
        backPath: '/admin/platform',
      };
    }
    throw new Error('Invalid owner type');
  }, [location.pathname, ownerId]);

  // ─── Mutations ─────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: (data: RbacRuleCreate) => rbacApi.createRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.all() });
      showSuccess('RBAC правило создано');
      navigate(ownerInfo.backPath);
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ──────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!formData.resource_id.trim()) {
      showError('ID ресурса не может быть пустым');
      return;
    }
    setSaving(true);
    try {
      await createMutation.mutateAsync({
        level: ownerInfo.level,
        resource_type: formData.resource_type,
        resource_id: formData.resource_id,
        effect: formData.effect,
        owner_user_id: ownerInfo.owner_user_id,
        owner_tenant_id: ownerInfo.owner_tenant_id,
        owner_platform: ownerInfo.owner_platform,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    navigate(ownerInfo.backPath);
  };

  // ─── Resource options for select ───────────────────────────────────

  const resourceOptions = useMemo(() => {
    if (formData.resource_type === 'agent') {
      return agents.map((a: any) => ({ value: a.id, label: `${a.name} (${a.slug})` }));
    }
    if (formData.resource_type === 'toolgroup') {
      return toolGroups.map((g: any) => ({ value: g.id, label: `${g.name} (${g.slug})` }));
    }
    return [];
  }, [formData.resource_type, agents, toolGroups]);

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <EntityPageV2
      title={`Новое RBAC правило для ${ownerInfo.title}`}
      mode="create"
      saving={saving}
    >
      <Tab 
        title="Создание правила" 
        layout="single"
        actions={[
          <Button key="save" variant="primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Создание...' : 'Создать'}
          </Button>,
          <Button key="cancel" variant="outline" onClick={handleCancel}>
            Отмена
          </Button>,
        ]}
      >
        {/* Owner info block */}
        <ContentBlock title="Владелец правила" icon="user">
          <div className={styles['form-grid']}>
            <div className={styles['form-field']}>
              <label className={styles.label}>Тип владельца</label>
              <Input value={ownerInfo.title} disabled />
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>ID владельца</label>
              <Input value={ownerId || 'Платформа'} disabled />
            </div>
            <div className={styles['form-field']}>
              <label className={styles.label}>Уровень правила</label>
              <div className={styles['badge-row']}>
                <Badge tone="neutral">{ownerInfo.level}</Badge>
              </div>
            </div>
          </div>
        </ContentBlock>

        {/* Rule configuration */}
        <ContentBlock title="Настройки правила" icon="settings">
          <div className={styles['form-grid']}>
            <div className={styles['form-field']}>
              <label className={styles.label}>Тип ресурса</label>
              <select
                className={styles.select}
                value={formData.resource_type}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    resource_type: e.target.value as ResourceType,
                    resource_id: '',
                  }))
                }
              >
                <option value="agent">Агент</option>
                <option value="toolgroup">Группа инструментов</option>
                <option value="tool">Инструмент</option>
                <option value="instance">Инстанс</option>
              </select>
            </div>

            <div className={styles['form-field']}>
              <label className={styles.label}>Ресурс</label>
              {resourceOptions.length > 0 ? (
                <select
                  className={styles.select}
                  value={formData.resource_id}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, resource_id: e.target.value }))
                  }
                >
                  <option value="">Выберите...</option>
                  {resourceOptions.map((opt: any) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  value={formData.resource_id}
                  onChange={(e: ChangeEvent<HTMLInputElement>) =>
                    setFormData((prev) => ({ ...prev, resource_id: e.target.value }))
                  }
                  placeholder="ID ресурса"
                />
              )}
            </div>

            <div className={styles['form-field']}>
              <label className={styles.label}>Эффект</label>
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
            </div>
          </div>
        </ContentBlock>
      </Tab>
    </EntityPageV2>
  );
}

export default RbacRuleCreatePage;

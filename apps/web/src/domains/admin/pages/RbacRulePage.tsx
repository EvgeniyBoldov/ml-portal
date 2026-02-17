/**
 * RbacRulePage - Просмотр/редактирование RBAC правила по правилам проекта
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
import Button from '@/shared/ui/Button';
import { RbacRuleBlock, RbacTargetBlock, type RbacRuleData, type RbacTargetData } from '@/shared/ui/RbacRuleBlock';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';

interface FormData {
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
    resource_type: 'agent',
    resource_id: '',
    effect: 'deny',
  });
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

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
        resource_type: rule.resource_type,
        resource_id: rule.resource_id,
        effect: rule.effect,
      });
    }
    setSearchParams({});
  };

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleDelete = async () => {
    // Удаление правила (если нужно)
    setShowDeleteConfirm(false);
  };

  const handleFieldChange = (key: keyof FormData, value: string) => {
    if (key === 'resource_type') {
      setFormData(prev => ({ 
        ...prev, 
        resource_type: value as ResourceType,
        resource_id: '' // Сбросить ресурс при смене типа
      }));
    } else {
      setFormData(prev => ({ ...prev, [key]: value }));
    }
  };

  // ─── Render ────────────────────────────────────────────────────────

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'RBAC', href: '/admin/platform/rbac' },
    { label: 'Правило' },
  ];

  // Данные для блоков
  const ruleData: RbacRuleData = {
    resource_type: formData.resource_type,
    resource_id: formData.resource_id,
    effect: formData.effect,
  };

  const targetData: RbacTargetData = rule ? {
    owner_user_id: rule.owner_user_id,
    owner_tenant_id: rule.owner_tenant_id,
    owner_platform: rule.owner_platform,
    created_at: rule.created_at,
    created_by_user_id: rule.created_by_user_id,
  } : {
    owner_platform: false,
    created_at: new Date().toISOString(),
  };

  return (
    <>
    <EntityPageV2
      title="RBAC правило"
      mode={mode}
      loading={isLoading}
      saving={saving}
      breadcrumbs={breadcrumbs}
      backPath="/admin/platform/rbac"
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
    >
      <Tab 
        title="Обзор" 
        layout="grid" 
        id="overview"
        actions={
          mode === 'view' ? [
            <Button key="edit" onClick={handleEdit}>
              Редактировать
            </Button>,
            <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              Удалить
            </Button>,
          ] : mode === 'edit' ? [
            <Button key="save" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : []
        }
      >
        {/* Первый блок - владелец */}
        <RbacTargetBlock data={targetData} editable={false} width="1/2" />
        
        {/* Второй блок - правило */}
        <RbacRuleBlock 
          data={ruleData}
          editable={isEditable}
          width="1/2"
          agents={agents}
          toolGroups={toolGroups}
          onChange={handleFieldChange}
        />
      </Tab>
    </EntityPageV2>

    {showDeleteConfirm && (
      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить RBAC правило?"
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    )}
    </>
  );
}

export default RbacRulePage;

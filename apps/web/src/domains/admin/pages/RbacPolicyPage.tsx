/**
 * RbacPolicyPage - View/Edit/Create RBAC policy with rules
 *
 * Not versioned — rules are mutable within a policy.
 * Uses EntityPage for view/edit/create modes.
 */
import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rbacApi, type RbacPolicyDetail, type RbacRule, type RbacRuleCreate, type RbacEffect, type ResourceType, type RbacLevel } from '@/shared/api/rbac';
import { agentsApi } from '@/shared/api/agents';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import {
  EntityPageV2,
  Tab,
  type EntityPageMode,
  type BreadcrumbItem,
} from '@/shared/ui/EntityPage/EntityPageV2';
import {
  ContentBlock,
  DataTable,
  Badge,
  Input,
  Select,
  type DataTableColumn,
} from '@/shared/ui';
import Button from '@/shared/ui/Button';
import styles from './RbacPolicyPage.module.css';

interface FormData {
  slug: string;
  name: string;
  description: string;
}

const LEVEL_LABELS: Record<string, string> = {
  platform: 'Платформа',
  tenant: 'Тенант',
  user: 'Пользователь',
};

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

export function RbacPolicyPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState<FormData>({ slug: '', name: '', description: '' });
  const [saving, setSaving] = useState(false);

  // ─── New rule form state ───────────────────────────────────────────
  const [newRule, setNewRule] = useState<{
    level: RbacLevel;
    level_id: string;
    resource_type: ResourceType;
    resource_id: string;
    effect: RbacEffect;
  }>({
    level: 'platform',
    level_id: '',
    resource_type: 'agent',
    resource_id: '',
    effect: 'deny',
  });
  const [showAddRule, setShowAddRule] = useState(false);

  // ─── Queries ───────────────────────────────────────────────────────

  const { data: policy, isLoading } = useQuery({
    queryKey: qk.rbac.detail(slug!),
    queryFn: () => rbacApi.getPolicy(slug!),
    enabled: !isCreate && !!slug,
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
      return apiRequest('/admin/tool-groups');
    },
  });

  // ─── Sync form ─────────────────────────────────────────────────────

  useEffect(() => {
    if (isCreate) {
      setFormData({ slug: '', name: '', description: '' });
    } else if (policy) {
      setFormData({
        slug: policy.slug,
        name: policy.name,
        description: policy.description || '',
      });
    }
  }, [policy, isCreate]);

  // ─── Mutations ─────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: () =>
      rbacApi.createPolicy({
        slug: formData.slug,
        name: formData.name,
        description: formData.description || undefined,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.all() });
      showSuccess('Набор RBAC создан');
      navigate(`/admin/rbac/${created.slug}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      rbacApi.updatePolicy(slug!, {
        name: formData.name,
        description: formData.description || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.rbac.list({}) });
      showSuccess('Набор RBAC обновлён');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const addRuleMutation = useMutation({
    mutationFn: (data: RbacRuleCreate) => rbacApi.createRule(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.detail(slug!) });
      showSuccess('Правило добавлено');
      setShowAddRule(false);
      setNewRule({ level: 'platform', level_id: '', resource_type: 'agent', resource_id: '', effect: 'deny' });
    },
    onError: (err: Error) => showError(err.message),
  });

  const toggleRuleMutation = useMutation({
    mutationFn: ({ ruleId, effect }: { ruleId: string; effect: RbacEffect }) =>
      rbacApi.updateRule(slug!, ruleId, { effect }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.detail(slug!) });
      showSuccess('Правило обновлено');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => rbacApi.deleteRule(slug!, ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.detail(slug!) });
      showSuccess('Правило удалено');
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ──────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!formData.name.trim()) {
      showError('Название не может быть пустым');
      return;
    }
    setSaving(true);
    try {
      if (isCreate) {
        if (!formData.slug.trim()) {
          showError('Slug не может быть пустым');
          return;
        }
        await createMutation.mutateAsync();
      } else {
        await updateMutation.mutateAsync();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (isCreate) {
      navigate('/admin/rbac');
    } else {
      if (policy) {
        setFormData({
          slug: policy.slug,
          name: policy.name,
          description: policy.description || '',
        });
      }
      setSearchParams({});
    }
  };

  const handleAddRule = () => {
    if (!newRule.resource_id) {
      showError('Выберите ресурс');
      return;
    }
    addRuleMutation.mutate({
      level: newRule.level,
      level_id: newRule.level === 'platform' ? null : newRule.level_id || null,
      resource_type: newRule.resource_type,
      resource_id: newRule.resource_id,
      effect: newRule.effect,
    });
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

  // ─── Resource options for select ───────────────────────────────────

  const resourceOptions = useMemo(() => {
    if (newRule.resource_type === 'agent') {
      return agents.map((a: any) => ({ value: a.id, label: `${a.name} (${a.slug})` }));
    }
    if (newRule.resource_type === 'toolgroup') {
      return toolGroups.map((g: any) => ({ value: g.id, label: `${g.name} (${g.slug})` }));
    }
    return [];
  }, [newRule.resource_type, agents, toolGroups]);

  // ─── Rules table ───────────────────────────────────────────────────

  const rules = policy?.rules || [];

  const ruleColumns: DataTableColumn<RbacRule>[] = [
    {
      key: 'level',
      label: 'УРОВЕНЬ',
      width: 120,
      render: (row) => (
        <Badge tone="neutral" size="small">
          {LEVEL_LABELS[row.level] || row.level}
        </Badge>
      ),
    },
    {
      key: 'resource_type',
      label: 'ТИП РЕСУРСА',
      width: 160,
      render: (row) => RESOURCE_TYPE_LABELS[row.resource_type] || row.resource_type,
    },
    {
      key: 'resource_id',
      label: 'РЕСУРС',
      render: (row) => getResourceName(row.resource_type, row.resource_id),
    },
    {
      key: 'effect',
      label: 'ЭФФЕКТ',
      width: 120,
      render: (row) => {
        const config = EFFECT_LABELS[row.effect];
        return (
          <Badge
            tone={config.tone}
            size="small"
            onClick={() => {
              const next = row.effect === 'allow' ? 'deny' : 'allow';
              toggleRuleMutation.mutate({ ruleId: row.id, effect: next as RbacEffect });
            }}
            style={{ cursor: 'pointer' }}
          >
            {config.label}
          </Badge>
        );
      },
    },
    {
      key: 'actions',
      label: '',
      width: 60,
      align: 'right',
      render: (row) => (
        <Button
          variant="ghost"
          size="small"
          onClick={(e: React.MouseEvent) => {
            e.stopPropagation();
            deleteRuleMutation.mutate(row.id);
          }}
        >
          ✕
        </Button>
      ),
    },
  ];

  // ─── Breadcrumbs ───────────────────────────────────────────────────

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'RBAC', href: '/admin/rbac' },
    { label: isCreate ? 'Новый набор' : policy?.name || slug || '' },
  ];

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <EntityPageV2
      title={isCreate ? 'Новый набор RBAC' : policy?.name || ''}
      mode={mode}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      backPath="/admin/rbac"
      onEdit={() => setSearchParams({ mode: 'edit' })}
      onSave={handleSave}
      onCancel={handleCancel}
    >
      <Tab title="Обзор" layout="single">
        {/* Metadata block */}
        <ContentBlock title="Основное" icon="settings">
        <div className={styles.formGrid}>
          <div className={styles.formField}>
            <label className={styles.label}>Slug</label>
            <Input
              value={formData.slug}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFormData((prev) => ({ ...prev, slug: e.target.value }))
              }
              placeholder="my-rbac-policy"
              disabled={!isCreate}
            />
          </div>
          <div className={styles.formField}>
            <label className={styles.label}>Название</label>
            <Input
              value={formData.name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFormData((prev) => ({ ...prev, name: e.target.value }))
              }
              placeholder="Название набора"
              disabled={!isEditable}
            />
          </div>
          <div className={styles.formField} style={{ gridColumn: '1 / -1' }}>
            <label className={styles.label}>Описание</label>
            <Input
              value={formData.description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFormData((prev) => ({ ...prev, description: e.target.value }))
              }
              placeholder="Описание набора правил"
              disabled={!isEditable}
            />
          </div>
        </div>
      </ContentBlock>

      {/* Rules block — only for existing policies */}
      {!isCreate && (
        <ContentBlock
          title={`Правила (${rules.length})`}
          icon="shield"
          headerActions={
            <Button variant="outline" size="small" onClick={() => setShowAddRule(!showAddRule)}>
              {showAddRule ? 'Отмена' : '+ Добавить правило'}
            </Button>
          }
        >
          {/* Add rule form */}
          {showAddRule && (
            <div className={styles.addRuleForm}>
              <div className={styles.addRuleRow}>
                <div className={styles.addRuleField}>
                  <label className={styles.label}>Уровень</label>
                  <select
                    className={styles.select}
                    value={newRule.level}
                    onChange={(e) =>
                      setNewRule((prev) => ({
                        ...prev,
                        level: e.target.value as RbacLevel,
                        level_id: e.target.value === 'platform' ? '' : prev.level_id,
                      }))
                    }
                  >
                    <option value="platform">Платформа</option>
                    <option value="tenant">Тенант</option>
                    <option value="user">Пользователь</option>
                  </select>
                </div>

                {newRule.level !== 'platform' && (
                  <div className={styles.addRuleField}>
                    <label className={styles.label}>
                      {newRule.level === 'tenant' ? 'Tenant ID' : 'User ID'}
                    </label>
                    <Input
                      value={newRule.level_id}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setNewRule((prev) => ({ ...prev, level_id: e.target.value }))
                      }
                      placeholder="UUID"
                    />
                  </div>
                )}

                <div className={styles.addRuleField}>
                  <label className={styles.label}>Тип ресурса</label>
                  <select
                    className={styles.select}
                    value={newRule.resource_type}
                    onChange={(e) =>
                      setNewRule((prev) => ({
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

                <div className={styles.addRuleField}>
                  <label className={styles.label}>Ресурс</label>
                  {resourceOptions.length > 0 ? (
                    <select
                      className={styles.select}
                      value={newRule.resource_id}
                      onChange={(e) =>
                        setNewRule((prev) => ({ ...prev, resource_id: e.target.value }))
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
                      value={newRule.resource_id}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setNewRule((prev) => ({ ...prev, resource_id: e.target.value }))
                      }
                      placeholder="UUID ресурса"
                    />
                  )}
                </div>

                <div className={styles.addRuleField}>
                  <label className={styles.label}>Эффект</label>
                  <select
                    className={styles.select}
                    value={newRule.effect}
                    onChange={(e) =>
                      setNewRule((prev) => ({ ...prev, effect: e.target.value as RbacEffect }))
                    }
                  >
                    <option value="deny">Запрещён</option>
                    <option value="allow">Разрешён</option>
                  </select>
                </div>
              </div>

              <div className={styles.addRuleActions}>
                <Button
                  variant="primary"
                  size="small"
                  onClick={handleAddRule}
                  disabled={addRuleMutation.isPending}
                >
                  {addRuleMutation.isPending ? 'Добавление...' : 'Добавить'}
                </Button>
              </div>
            </div>
          )}

          {/* Rules table */}
          <DataTable
            columns={ruleColumns}
            data={rules}
            keyField="id"
            emptyText="Нет правил. Нажмите «+ Добавить правило» для создания."
          />
        </ContentBlock>
      </Tab>
    </EntityPageV2>
  );
}

export default RbacPolicyPage;

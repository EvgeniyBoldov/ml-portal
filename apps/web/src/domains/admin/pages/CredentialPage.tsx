/**
 * CredentialPage — просмотр/создание/редактирование/удаление credential.
 *
 * Использует useEntityEditor для стандартной CRUD логики.
 * Payload — вложенный объект, обрабатывается через handleFieldChange.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { credentialsApi, type Credential, type CredentialCreate } from '@/shared/api/credentials';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import { useEntityEditor } from '@/shared/hooks/useEntityEditor';
import { EntityPageV2, Tab, type BreadcrumbItem } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Badge, Button, ConfirmDialog } from '@/shared/ui';

const AUTH_TYPE_LABELS: Record<string, string> = {
  token: 'Bearer Token',
  basic: 'Basic Auth',
  api_key: 'API Key',
  oauth: 'OAuth 2.0',
};

const AUTH_TYPE_OPTIONS = [
  { value: 'token', label: AUTH_TYPE_LABELS.token },
  { value: 'basic', label: AUTH_TYPE_LABELS.basic },
  { value: 'api_key', label: AUTH_TYPE_LABELS.api_key },
  { value: 'oauth', label: AUTH_TYPE_LABELS.oauth },
];

/* ─── Field configs ─── */

// Get payload fields based on auth type
const getPayloadFields = (authType: string): FieldConfig[] => {
  const fields: Record<string, FieldConfig[]> = {
    token: [
      { key: 'payload.token', type: 'password', label: 'Token', required: true },
    ],
    basic: [
      { key: 'payload.username', type: 'text', label: 'Имя пользователя', required: true },
      { key: 'payload.password', type: 'password', label: 'Пароль', required: true },
    ],
    api_key: [
      { key: 'payload.api_key', type: 'password', label: 'API Key', required: true },
    ],
    oauth: [
      { key: 'payload.client_id', type: 'text', label: 'Client ID', required: true },
      { key: 'payload.client_secret', type: 'password', label: 'Client Secret', required: true },
    ],
  };
  
  return fields[authType] || [];
};

// Get payload template
const getPayloadTemplate = (authType: string): Record<string, string> => {
  const fields = getPayloadFields(authType);
  const template: Record<string, string> = {};
  fields.forEach(field => {
    const key = field.key.replace('payload.', '');
    template[key] = '';
  });
  return template;
};

const BASE_FIELDS: FieldConfig[] = [
  {
    key: 'instance_id',
    type: 'select',
    label: 'Коннектор',
    required: true,
    description: 'Удалённый коннектор для этого доступа',
  },
  {
    key: 'auth_type',
    type: 'select',
    label: 'Тип авторизации',
    required: true,
    description: 'Способ аутентификации с коннектором',
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'is_active', type: 'badge', label: 'Статус', editable: false },
  { key: 'created_at', type: 'date', label: 'Создан', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлен', editable: false },
];

function normalizeMaskedPayload(
  authType: string,
  maskedPayload: Record<string, string> | null | undefined,
  hasPayload: boolean | undefined,
): Record<string, string> {
  const template = getPayloadTemplate(authType);
  const source = maskedPayload ?? {};
  const result: Record<string, string> = {};
  Object.keys(template).forEach((key) => {
    const raw = source[key];
    if (raw && String(raw).trim()) {
      const len = String(raw).length;
      result[key] = '*'.repeat(Math.max(len, 3));
      return;
    }
    result[key] = hasPayload ? '********' : '';
  });
  return result;
}

function prefixedPayload(payload: Record<string, string> | Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  Object.entries(payload).forEach(([key, value]) => {
    result[`payload.${key}`] = value;
  });
  return result;
}

/* ─── Component ─── */

export default function CredentialPage() {
  const {
    mode,
    isNew,
    isEditable,
    entity: credential,
    isLoading,
    formData,
    saving,
    showDeleteConfirm,
    setShowDeleteConfirm,
    breadcrumbs,
    handleFieldChange: baseHandleFieldChange,
    handleSave,
    handleEdit,
    handleCancel,
    handleDelete,
    handleDeleteConfirm,
  } = useEntityEditor<Credential, CredentialCreate, Partial<CredentialCreate>>({
    entityType: 'credential',
    entityNameLabel: 'Доступы',
    entityTypeLabel: 'доступ',
    basePath: '/admin/credentials',
    listPath: '/admin/platform',
    api: {
      get: (id) => credentialsApi.get(id),
      create: (data) => credentialsApi.create(data),
      update: (id, data) => credentialsApi.update(id, data),
      delete: (id) => credentialsApi.delete(id),
    },
    queryKeys: {
      list: qk.credentials.list({}),
      detail: (id) => qk.credentials.detail(id),
    },
    getInitialFormData: (cred) => ({
      instance_id: cred?.instance_id ?? '',
      auth_type: cred?.auth_type ?? 'token',
      payload: cred ? getPayloadTemplate(cred.auth_type) : getPayloadTemplate('token'),
      owner_platform: cred?.owner_platform ?? true,
    }),
    transformCreate: (data) => ({
      instance_id: data.instance_id ?? '',
      auth_type: data.auth_type ?? 'token',
      payload: data.payload ?? {},
      owner_platform: true,
    }),
    transformUpdate: (data) => ({
      instance_id: data.instance_id,
      auth_type: data.auth_type,
      payload: data.payload ?? {},
      owner_platform: true,
    }),
    messages: {
      create: 'Доступ создан',
      update: 'Доступ обновлён',
      delete: 'Доступ удалён',
    },
  });

  // ─── Payload field change — вложенные ключи ───
  const handleFieldChange = (key: string, value: any) => {
    if (key.startsWith('payload.')) {
      const payloadKey = key.replace('payload.', '');
      baseHandleFieldChange('payload', { ...(formData.payload ?? {}), [payloadKey]: value });
    } else if (key === 'auth_type') {
      baseHandleFieldChange('auth_type', value);
      baseHandleFieldChange('payload', getPayloadTemplate(value));
    } else {
      baseHandleFieldChange(key, value);
    }
  };

  // ─── Коннекторы для select ───
  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({ placement: 'remote' }),
    queryFn: () => toolInstancesApi.list({ placement: 'remote' }),
    staleTime: 60_000,
  });

  const remoteInstances = instances.filter((i: ToolInstance) => i.placement === 'remote');

  const instanceOptions = useMemo(
    () => remoteInstances.map((i: ToolInstance) => ({ value: i.id, label: i.name })),
    [remoteInstances]
  );

  // ─── Динамические поля ───
  const payloadFields = useMemo(
    () => getPayloadFields(formData.auth_type ?? 'token'),
    [formData.auth_type]
  );

  const mainFields = useMemo(() => {
    const baseWithOpts = BASE_FIELDS.map((f) => ({
      ...f,
      options: f.key === 'instance_id' ? instanceOptions : AUTH_TYPE_OPTIONS,
    }));
    return [...baseWithOpts, ...payloadFields];
  }, [instanceOptions, payloadFields]);

  // ─── Derived ───
  const mainData = isEditable
    ? {
        instance_id: formData.instance_id,
        auth_type: formData.auth_type,
        ...prefixedPayload((formData.payload ?? {}) as Record<string, unknown>),
      }
    : {
        instance_id: credential?.instance_id ?? '',
        auth_type: credential?.auth_type ?? 'token',
        ...prefixedPayload(
          normalizeMaskedPayload(
            credential?.auth_type ?? 'token',
            credential?.masked_payload,
            credential?.has_payload,
          ),
        ),
      };

  const metaData = {
    is_active: credential?.is_active ? 'Активен' : 'Неактивен',
    created_at: credential?.created_at ?? '',
    updated_at: '',
  };

  const instanceName = remoteInstances.find((i) => i.id === (credential?.instance_id ?? formData.instance_id))?.name ?? 'Доступ';

  // ─── Create mode ───
  if (isNew) {
    return (
      <EntityPageV2
        title="Новый доступ"
        mode="create"
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/platform"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <Block
            title="Основные настройки"
            icon="key"
            iconVariant="primary"
            width="1/2"
            fields={mainFields}
            data={mainData}
            editable
            onChange={handleFieldChange}
          />
          <Block
            title="Статус и даты"
            icon="clock"
            iconVariant="info"
            width="1/2"
            fields={META_FIELDS}
            data={metaData}
          />
        </Tab>
      </EntityPageV2>
    );
  }

  // ─── View / Edit mode ───
  return (
    <>
      <EntityPageV2
        title={instanceName}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
        actionButtons={
          mode === 'view' ? (
            <>
              <Button onClick={handleEdit}>Редактировать</Button>
              <Button variant="danger" onClick={handleDelete}>Удалить</Button>
            </>
          ) : undefined
        }
      >
        <Tab title="Обзор" layout="grid" id="overview">
          <Block
            title="Основные настройки"
            icon="key"
            iconVariant="primary"
            width="1/2"
            fields={mainFields}
            data={mainData}
            editable={isEditable}
            onChange={handleFieldChange}
            headerActions={
              credential ? (
                <Badge tone={credential.is_active ? 'success' : 'neutral'}>
                  {credential.is_active ? 'Активен' : 'Неактивен'}
                </Badge>
              ) : undefined
            }
          />
          <Block
            title="Статус и даты"
            icon="clock"
            iconVariant="info"
            width="1/2"
            fields={META_FIELDS}
            data={metaData}
          />
        </Tab>

        <Tab title="Журнал" layout="full" id="activity">
          <Block title="Активность" icon="clock" iconVariant="info" width="full">
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
              Журнал активности credential будет доступен в следующих версиях
            </div>
          </Block>
        </Tab>
      </EntityPageV2>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить доступ?"
        description="Это действие необратимо."
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}

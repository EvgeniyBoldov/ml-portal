/**
 * CredentialPage - создание/просмотр/редактирование credential
 * 
 * Режимы:
 * - new - создание нового credential
 * - {id} - просмотр/редактирование существующего credential
 * - mode=edit - режим редактирования
 */
import { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi, type Credential, type CredentialCreate } from '@/shared/api/credentials';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { ContentBlock, Input, Select, Badge, type FieldDefinition } from '@/shared/ui';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

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

const containerFields: FieldDefinition[] = [
  {
    key: 'instance_id',
    label: 'Инстанс',
    type: 'select',
    required: true,
    options: [], // Заполняется динамически
  },
  {
    key: 'auth_type',
    label: 'Тип авторизации',
    type: 'select',
    required: true,
    options: AUTH_TYPE_OPTIONS,
  },
  {
    key: 'is_active',
    label: 'Статус',
    type: 'boolean',
    editable: false, // Только для просмотра
  },
  {
    key: 'created_at',
    label: 'Создан',
    type: 'date',
    editable: false, // Только для просмотра
  },
];

// Получение полей payload в зависимости от типа авторизации
const getPayloadFields = (authType: string): FieldDefinition[] => {
  const fields: Record<string, FieldDefinition[]> = {
    token: [
      { key: 'token', label: 'Token', type: 'text', required: true },
    ],
    basic: [
      { key: 'username', label: 'Имя пользователя', type: 'text', required: true },
      { key: 'password', label: 'Пароль', type: 'text', required: true },
    ],
    api_key: [
      { key: 'key', label: 'API Key', type: 'text', required: true },
    ],
    oauth: [
      { key: 'client_id', label: 'Client ID', type: 'text', required: true },
      { key: 'client_secret', label: 'Client Secret', type: 'text', required: true },
    ],
  };
  
  return fields[authType] || [];
};

// Получение шаблона payload
const getPayloadTemplate = (authType: string): Record<string, string> => {
  const fields = getPayloadFields(authType);
  const template: Record<string, string> = {};
  fields.forEach(field => {
    template[field.key] = '';
  });
  return template;
};

export default function CredentialPage() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = id === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  // Form state
  const [formData, setFormData] = useState({
    instance_id: '',
    auth_type: 'token',
    payload: getPayloadTemplate('token'),
    is_active: 'inactive',
    created_at: '',
  });

  // Queries
  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list(),
    queryFn: () => toolInstancesApi.list(),
  });

  const { data: credential, isLoading } = useQuery({
    queryKey: qk.credentials.detail(id!),
    queryFn: () => credentialsApi.get(id!),
    enabled: !isCreate && !!id,
  });

  // Filter remote instances only
  const remoteInstances = instances.filter((i: ToolInstance) => i.instance_type === 'remote');
  const instanceOptions = remoteInstances.map((i: ToolInstance) => ({
    value: i.id,
    label: i.name,
  }));

  // Поля для первого ContentBlock (основные данные + секреты)
  const mainFields: FieldDefinition[] = [
    {
      key: 'instance_id',
      label: 'Инстанс',
      type: 'select',
      required: true,
      options: instanceOptions,
    },
    {
      key: 'auth_type',
      label: 'Тип авторизации',
      type: 'select',
      required: true,
      options: AUTH_TYPE_OPTIONS,
    },
    ...getPayloadFields(formData.auth_type || 'token').map(field => ({
      ...field,
      type: 'text' as const,
    })),
  ];

  // Поля для второго ContentBlock (статус и даты)
  const statusFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Статус',
      type: 'badge',
      badgeTone: (credential?.is_active || formData.is_active === 'active') ? 'success' : 'neutral',
    },
    {
      key: 'created_at',
      label: 'Создан',
      type: 'date',
    },
  ];

  // Sync form data
  useEffect(() => {
    if (credential) {
      setFormData({
        instance_id: credential.instance_id,
        auth_type: credential.auth_type,
        payload: credential.payload || {},
        is_active: credential.is_active ? 'active' : 'inactive',
        created_at: credential.created_at,
      });
    }
  }, [credential]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: CredentialCreate) => credentialsApi.create(data),
    onSuccess: () => {
      showSuccess('Credential создан');
      queryClient.invalidateQueries({ queryKey: qk.credentials.all() });
      navigate('/admin/credentials');
    },
    onError: () => {
      showError('Не удалось создать credential');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CredentialCreate> }) =>
      credentialsApi.update(id, data),
    onSuccess: () => {
      showSuccess('Credential обновлён');
      queryClient.invalidateQueries({ queryKey: qk.credentials.all() });
      queryClient.invalidateQueries({ queryKey: qk.credentials.detail(id!) });
      setSearchParams({});
    },
    onError: () => {
      showError('Не удалось обновить credential');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.delete(id),
    onSuccess: () => {
      showSuccess('Credential удалён');
      queryClient.invalidateQueries({ queryKey: qk.credentials.all() });
      navigate('/admin/credentials');
    },
    onError: () => {
      showError('Не удалось удалить credential');
    },
  });

  // Handlers
  const handleSave = async () => {
    if (!formData.instance_id) {
      showError('Выберите инстанс');
      return;
    }

    try {
      const data: CredentialCreate = {
        instance_id: formData.instance_id,
        auth_type: formData.auth_type,
        payload: formData.payload,
        owner_platform: true, // Platform-level credentials
      };

      if (isCreate) {
        await createMutation.mutateAsync(data);
      } else {
        await updateMutation.mutateAsync({ id: id!, data });
      }
    } catch (error) {
      // Error handled in mutation
    }
  };

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (isCreate) {
      navigate('/admin/credentials');
    } else {
      setSearchParams({});
    }
  };

  const handleDelete = () => {
    if (id && window.confirm('Удалить этот credential?')) {
      deleteMutation.mutate(id);
    }
  };

  // Breadcrumbs
  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Общие доступы', href: '/admin/credentials' },
    { label: isCreate ? 'Новый доступ' : 'Доступ' },
  ];

  const instanceName = remoteInstances.find(i => i.id === formData.instance_id)?.name || formData.instance_id;
  const saving = createMutation.isPending || updateMutation.isPending;

  // Create mode — single tab, single column
  if (isCreate) {
    return (
      <EntityPageV2
        title="Новый доступ"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/credentials"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="grid">
          <ContentBlock 
            title="Основные настройки" 
            icon="key" 
            width="full" 
            fields={mainFields}
            data={formData}
            onChange={(key: string, value: any) => {
              setFormData((prev: any) => ({ ...prev, [key]: value }));
              if (key === 'auth_type') {
                setFormData((prev: any) => ({
                  ...prev,
                  auth_type: value,
                  payload: getPayloadTemplate(value),
                }));
              }
            }}
          />
          <ContentBlock 
            title="Статус и даты" 
            icon="clock" 
            width="full" 
            fields={statusFields}
            data={formData}
            onChange={(key: string, value: any) => {
              setFormData((prev: any) => ({ ...prev, [key]: value }));
            }}
          />
        </Tab>
      </EntityPageV2>
    );
  }

  // View/Edit mode — two tabs
  return (
    <>
      <EntityPageV2
        title={instanceName || 'Доступ'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
        onDelete={handleDelete}
      >
        <Tab title="Обзор" layout="grid" id="overview">
          <ContentBlock 
            title="Основные настройки" 
            icon="key" 
            width="full" 
            editable={isEditable}
            fields={mainFields}
            data={mode === 'edit' ? formData : (credential || formData)}
            onChange={(key: string, value: any) => {
              setFormData((prev: any) => ({ ...prev, [key]: value }));
              if (key === 'auth_type') {
                setFormData((prev: any) => ({
                  ...prev,
                  auth_type: value,
                  payload: getPayloadTemplate(value),
                }));
              }
            }}
          />
          <ContentBlock 
            title="Статус и даты" 
            icon="clock" 
            width="full" 
            editable={false}
            fields={statusFields}
            data={credential || formData}
            onChange={() => {}} // Статус и даты не редактируются
          />
        </Tab>

        <Tab title="Журнал" layout="full" id="activity">
          <ContentBlock title="Активность" icon="clock">
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
              Журнал активности credential будет доступен в следующих версиях
            </div>
          </ContentBlock>
        </Tab>
      </EntityPageV2>
    </>
  );
}

/**
 * UserPage - Admin page for managing Users
 * 
 * Uses Block + GridLayout system for structured layout.
 * Data flows: API types → formData state → Block fields.
 * No mappers, no intermediate interfaces.
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useUser, useUpdateUser, useCreateUser, useSetUserPassword } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import { qk } from '@shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui/EntityPage';
import { buildEntityCrudActions, composeEntityActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Badge, Button, LifecycleDeleteDialog, Modal } from '@/shared/ui';
import LifecycleRestoreDialog from '@/shared/ui/LifecycleRestoreDialog';
import Input from '@/shared/ui/Input';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable/RBACRulesTable';
import type { User, Tenant } from '@shared/api/admin';
import { CredentialsPanel, FactsPanel } from '@/shared/ui';

/* ─── SetPasswordModal ─── */

function SetPasswordModal({
  open,
  onClose,
  onConfirm,
  saving,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (password: string) => void;
  saving: boolean;
}) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setPassword(''); setConfirm(''); setError(''); setRevealed(false); }
  }, [open]);

  const handleSubmit = () => {
    if (password.length < 8) { setError('Минимум 8 символов'); return; }
    if (password !== confirm) { setError('Пароли не совпадают'); return; }
    setError('');
    onConfirm(password);
  };

  return (
    <Modal
      open={open}
      title="Установить пароль"
      onClose={onClose}
      footer={
        <>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? 'Сохранение...' : 'Установить'}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={saving}>Отмена</Button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <label style={{ display: 'block', marginBottom: '0.375rem', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)' }}>Новый пароль</label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Input
              type={revealed ? 'text' : 'password'}
              value={password}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
              placeholder="Минимум 8 символов"
              autoComplete="new-password"
            />
            <Button size="sm" variant="ghost" onClick={() => setRevealed(v => !v)} type="button">
              {revealed ? '🙈' : '👁'}
            </Button>
          </div>
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.375rem', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)' }}>Повторите пароль</label>
          <Input
            type={revealed ? 'text' : 'password'}
            value={confirm}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirm(e.target.value)}
            placeholder="Повторите пароль"
            autoComplete="new-password"
          />
        </div>
        {error && (
          <div style={{ color: 'var(--color-danger, #e74c3c)', fontSize: '0.875rem' }}>{error}</div>
        )}
      </div>
    </Modal>
  );
}

/* ─── Constants ─── */

/* ─── Field configs ─── */

const BASE_INFO_FIELDS: Omit<FieldConfig, 'options'>[] = [
  { key: 'full_name', type: 'text', label: 'Имя', editable: false },
  {
    key: 'login',
    type: 'text',
    label: 'Логин',
    description: 'Уникальный идентификатор пользователя',
    editable: false,
    placeholder: 'Введите логин',
  },
  {
    key: 'email',
    type: 'text',
    label: 'Email',
    editable: false,
    placeholder: 'user@example.com',
  },
  {
    key: 'tenant_id',
    type: 'select',
    label: 'Рабочая группа',
    description: 'Основная рабочая группа пользователя',
  },
];

const BASE_INFO_FIELDS_CREATE: Omit<FieldConfig, 'options'>[] = [
  {
    key: 'full_name',
    type: 'text',
    label: 'Имя',
    placeholder: 'Введите имя пользователя',
  },
  {
    key: 'login',
    type: 'text',
    label: 'Логин',
    description: 'Уникальный идентификатор пользователя',
    editable: true,
    placeholder: 'Введите логин',
  },
  {
    key: 'email',
    type: 'text',
    label: 'Email',
    placeholder: 'user@example.com',
  },
  {
    key: 'password',
    type: 'password',
    label: 'Пароль локальной учётной записи',
    description: 'LDAP-пользователи создаются автоматически при первом входе',
    required: true,
    placeholder: 'Минимум 8 символов',
  },
  {
    key: 'tenant_id',
    type: 'select',
    label: 'Рабочая группа',
    description: 'Основная рабочая группа пользователя',
  },
];

const STATUS_FIELDS: FieldConfig[] = [
  {
    key: 'account_type',
    type: 'custom',
    label: 'Тип учётной записи',
    editable: false,
    render: (value) => {
      const accountType = typeof value === 'string' ? value : '—';
      return <Badge tone={accountType === 'LDAP' ? 'info' : 'success'}>{accountType}</Badge>;
    },
  },
  { key: 'deactivated_reason', type: 'text', label: 'Причина отключения', editable: false },
  {
    key: 'is_active',
    type: 'boolean',
    label: 'Активен',
    description: 'Пользователь может входить в систему',
  },
  {
    key: 'is_admin',
    type: 'boolean',
    label: 'Администратор платформы',
    description: 'Даёт доступ к административной панели',
  },
  {
    key: 'lifecycle_status',
    type: 'text',
    label: 'Lifecycle',
    description: 'Состояние lifecycle сущности',
    editable: false,
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
  { key: 'created_at', type: 'date', label: 'Создан', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлен', editable: false },
  { key: 'last_login_at', type: 'date', label: 'Последний вход', editable: false },
];

/* ─── Component ─── */

export function UserPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !id || id === 'new';
  const modeParam = searchParams.get('mode');
  const mode: EntityPageMode = isNew ? 'create' : (modeParam as EntityPageMode) || 'view';

  const [formData, setFormData] = useState({
    login: '',
    full_name: '',
    email: '',
    password: '',
    is_admin: false,
    tenant_id: '',
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);
  const [showSetPassword, setShowSetPassword] = useState(false);
  const [setPasswordSaving, setSetPasswordSaving] = useState(false);

  // ─── Queries ───
  const { data: user, isLoading, refetch } = useUser(isNew ? undefined : id);
  const { tenants } = useTenants(true);

  // ─── Sync form ←→ API ───
  useEffect(() => {
    if (user) {
      setFormData({
        login: user.login || '',
        full_name: user.full_name || '',
        email: user.email || '',
        password: '',
        is_admin: Boolean(user.is_admin),
        tenant_id: user.tenant_id ?? '',
        is_active: user.is_active,
      });
    }
  }, [user]);

  // ─── Mutations ───
  const createMutation = useCreateUser();
  const updateMutation = useUpdateUser();
  const setPasswordMutation = useSetUserPassword();

  // ─── Handlers ───
  const handleFieldChange = (key: string, value: unknown) => {
    if (key === 'login' || key === 'full_name' || key === 'email' || key === 'password' || key === 'tenant_id') {
      setFormData(prev => ({ ...prev, [key]: String(value ?? '') }));
    } else if (key === 'is_admin' && typeof value === 'boolean') {
      setFormData(prev => ({ ...prev, is_admin: value }));
    } else if (key === 'is_active' && typeof value === 'boolean') {
      setFormData(prev => ({ ...prev, is_active: value }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        if (!formData.login.trim()) { showError('Логин обязателен'); return; }
        if (!formData.password.trim()) { showError('Пароль обязателен'); return; }
        await createMutation.mutateAsync({
          login: formData.login,
          full_name: formData.full_name.trim() || null,
          email: formData.email || null,
          password: formData.password,
          role: 'reader',
          is_admin: formData.is_admin,
          tenant_id: formData.tenant_id || null,
          is_active: formData.is_active,
        });
        showSuccess('Пользователь создан');
        navigate('/admin/users');
      } else {
        await updateMutation.mutateAsync({
          id: id!,
          data: {
            ...(isLocalAccount ? {
              login: formData.login.trim(),
              full_name: formData.full_name.trim() || null,
              email: formData.email || null,
            } : {}),
            is_admin: formData.is_admin,
            is_active: formData.is_active,
            tenant_id: formData.tenant_id || null,
          },
        });
        showSuccess('Пользователь обновлён');
        setSearchParams({});
        refetch();
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/users');
    } else {
      if (user) {
        setFormData({
          login: user.login || '',
          full_name: user.full_name || '',
          email: user.email || '',
          password: '',
          is_admin: Boolean(user.is_admin),
          tenant_id: user.tenant_id ?? '',
          is_active: user.is_active,
        });
      }
      setSearchParams({});
    }
  };

  const handleDelete = () => setShowDeleteConfirm(true);

  const handleSetPassword = async (newPassword: string) => {
    if (!id) return;
    setSetPasswordSaving(true);
    try {
      await setPasswordMutation.mutateAsync({ id, newPassword });
      showSuccess('Пароль установлен');
      setShowSetPassword(false);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка установки пароля');
    } finally {
      setSetPasswordSaving(false);
    }
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Пользователи', href: '/admin/users' },
    { label: user?.full_name || user?.login || 'Новый пользователь' },
  ];

  // ─── Derived data for blocks ───
  const isLocalAccount = isNew || (user?.auth_provider ?? 'local') === 'local';
  const accountType = isLocalAccount ? 'Локальная' : 'LDAP';
  const infoData = (mode === 'edit' || isNew)
    ? formData
    : {
        login: user?.login || '',
        full_name: user?.full_name || '',
        email: user?.email || '',
        password: '',
        tenant_id: user?.tenant_id || '',
      };

  const statusData = mode === 'edit'
    ? {
        ...formData,
        account_type: accountType,
        deactivated_reason: user?.deactivated_reason || '',
        lifecycle_status: user?.lifecycle_status || 'active',
      }
    : {
        is_active: user?.is_active || false,
        is_admin: Boolean(user?.is_admin),
        account_type: accountType,
        deactivated_reason: user?.deactivated_reason || '',
        lifecycle_status: user?.lifecycle_status || 'active',
      };

  const metaData = {
    id: user?.id || '',
    created_at: user?.created_at || '',
    updated_at: user?.updated_at || '',
    last_login_at: user?.last_login_at || '',
  };

  // Options for selects
  const tenantOptions = [
    { value: '', label: '— Не выбран —' },
    ...(tenants || []).map((t: Tenant) => ({
      value: t.id,
      label: t.name,
    })),
  ];

  const infoFields: FieldConfig[] = BASE_INFO_FIELDS.map(f =>
    f.key === 'tenant_id'
      ? { ...f, options: tenantOptions }
      : ['full_name', 'login', 'email'].includes(f.key)
        ? { ...f, editable: isLocalAccount }
        : f as FieldConfig
  );

  const infoFieldsCreate: FieldConfig[] = BASE_INFO_FIELDS_CREATE.map(f =>
    f.key === 'tenant_id'
      ? { ...f, options: tenantOptions }
      : f as FieldConfig
  );

  // ─── Create mode ───
  if (isNew) {
    return (
      <>
        <EntityPageV2
          title="Новый пользователь"
          mode={mode}
          saving={saving}
          breadcrumbs={breadcrumbs}
          backPath="/admin/users"
          onSave={handleSave}
          onCancel={handleCancel}
        >
          <Tab title="Создание" layout="single">
            <Block
              title="Основная информация"
              icon="user"
              iconVariant="info"
              width="1/2"
              fields={infoFieldsCreate}
              data={infoData}
              editable={true}
              onChange={handleFieldChange}
            />
            <Block
              title="Статус и роль"
              icon="shield"
              iconVariant="warning"
              width="full"
              fields={STATUS_FIELDS}
              data={{ ...formData, account_type: 'Локальная', deactivated_reason: '' }}
              editable={true}
              onChange={handleFieldChange}
            />
          </Tab>
        </EntityPageV2>
      </>
    );
  }

  // ─── View / Edit mode ───
  return (
    <>
      <EntityPageV2
        title={user?.full_name || user?.login || 'Пользователь'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onSave={handleSave}
        onCancel={handleCancel}
        onDelete={handleDelete}
      >
        <Tab
          title="Обзор"
          layout="grid"
          id="overview"
          actions={composeEntityActions({
            crud: buildEntityCrudActions({
              mode,
              saving,
              tone: 'default',
              lifecycleStatus: user?.lifecycle_status,
              onEdit: handleEdit,
              onSave: handleSave,
              onCancel: handleCancel,
              onDelete: handleDelete,
              onRestore: () => setShowRestoreConfirm(true),
              restorePending: showRestoreConfirm,
            }),
            extra: mode === 'view' && isLocalAccount
              ? [
                  <Button key="set-pwd" variant="success" onClick={() => setShowSetPassword(true)}>
                    Установить пароль
                  </Button>,
                ]
              : [],
            extraPosition: 'beforeCrud',
          })}
        >
          {/* Row 1: Info (1/2) + Tenant (1/2) */}
          <Block
            title="Основная информация"
            icon="user"
            iconVariant="info"
            width="1/2"
            fields={infoFields}
            data={infoData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />
          {/* Row 2: Status */}
          <Block
            title="Статус и роль"
            icon="shield"
            iconVariant="warning"
            width="1/2"
            fields={STATUS_FIELDS}
            data={statusData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Метаданные"
            icon="database"
            iconVariant="info"
            width="full"
            fields={META_FIELDS}
            data={metaData}
          />
        </Tab>

        {!isNew && (
        <Tab title="Credentials" layout="full" id="credentials">
          <CredentialsPanel mode="readonly-owner" ownerUserId={id} />
        </Tab>
        )}

        {!isNew && (
        <Tab title="Факты" layout="full" id="facts">
          <FactsPanel mode="admin-user" ownerId={id} />
        </Tab>
        )}

        {!isNew && (
        <Tab 
          title="RBAC правила" 
          layout="full"
          id="rbac"
        >
            <RBACRulesTable mode="user" ownerId={id} />
        </Tab>
        )}
      </EntityPageV2>

      <SetPasswordModal
        open={showSetPassword}
        onClose={() => setShowSetPassword(false)}
        onConfirm={handleSetPassword}
        saving={setPasswordSaving}
      />

      <LifecycleDeleteDialog
        open={showDeleteConfirm}
        kind="user"
        entityId={id || ''}
        entityLabel={user?.login || 'Пользователь'}
        onCancel={() => setShowDeleteConfirm(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: qk.admin.users.all() });
          queryClient.invalidateQueries({ queryKey: qk.admin.users.detail(id || '') });
          showSuccess('Операция удаления выполнена');
          setShowDeleteConfirm(false);
          navigate('/admin/users');
        }}
      />

      <LifecycleRestoreDialog
        open={showRestoreConfirm}
        kind="user"
        entityId={id || ''}
        entityLabel={user?.login || 'Пользователь'}
        onCancel={() => setShowRestoreConfirm(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: qk.admin.users.all() });
          queryClient.invalidateQueries({ queryKey: qk.admin.users.detail(id || '') });
          showSuccess('Пользователь восстановлен');
          setShowRestoreConfirm(false);
        }}
      />
    </>
  );
}

export default UserPage;

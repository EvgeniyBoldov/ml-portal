/**
 * CredentialsPanel - панель управления credentials.
 *
 * Только список credential с DataTable.
 * Создание/редактирование - на отдельной странице CredentialPage.
 *
 * mode:
 * - platform: platform-level креды
 * - user: user/tenant креды с переключателем
 */
import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi, type Credential, type CredentialInstance } from '@/shared/api/credentials';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import Button from '../Button';
import Badge from '../Badge';
import Toggle from '../Toggle';
import DataTable, { type DataTableColumn } from '../DataTable/DataTable';
import ConfirmDialog from '../ConfirmDialog';
import Modal from '../Modal';
import Input from '../Input';
import Select from '../Select';
import { useErrorToast, useSuccessToast } from '../Toast';
import styles from './CredentialsPanel.module.css';

export type CredentialsPanelMode = 'platform' | 'user' | 'readonly-owner';

export interface CredentialsPanelProps {
  mode: CredentialsPanelMode;
  userId?: string;
  tenantId?: string;
  ownerUserId?: string;
  ownerTenantId?: string;
}

const AUTH_TYPE_LABELS: Record<string, string> = {
  token: 'Bearer Token',
  basic: 'Basic Auth',
  api_key: 'API Key Header',
  litellm_api_key: 'LiteLLM API Key',
  oauth: 'OAuth 2.0',
};

export function CredentialsPanel({ mode, userId, tenantId, ownerUserId, ownerTenantId }: CredentialsPanelProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [isTenantLevel, setIsTenantLevel] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedInstanceId, setSelectedInstanceId] = useState('');
  const [authType, setAuthType] = useState('token');
  const [payload, setPayload] = useState<Record<string, string>>({ token: '' });

  // ─── Queries ───────────────────────────────────────────────────────

  const listParams = useMemo(() => {
    if (mode === 'platform') {
      return { owner_platform: true };
    }
    if (mode === 'readonly-owner') return {};
    if (isTenantLevel && tenantId) {
      return { owner_tenant_id: tenantId };
    }
    if (userId) {
      return { owner_user_id: userId };
    }
    return {};
  }, [mode, isTenantLevel, userId, tenantId]);

  const { data: credentials = [], isLoading } = useQuery({
    queryKey: mode === 'readonly-owner'
      ? qk.credentials.list({ owner_user_id: ownerUserId, owner_tenant_id: ownerTenantId, summary: true })
      : mode === 'user'
        ? qk.profile.credentials(isTenantLevel ? 'tenant' : 'user')
        : qk.credentials.list(listParams),
    queryFn: () => mode === 'readonly-owner'
      ? credentialsApi.listSummary({ owner_user_id: ownerUserId, owner_tenant_id: ownerTenantId })
      : mode === 'user'
        ? credentialsApi.listProfile(isTenantLevel ? 'tenant' : 'user')
        : credentialsApi.list(listParams),
    enabled: mode !== 'readonly-owner' || Boolean(ownerUserId || ownerTenantId),
  });

  const { data: allInstances = [] } = useQuery({
    queryKey: mode === 'user' ? qk.profile.credentialInstances() : qk.toolInstances.list(),
    queryFn: (): Promise<ToolInstance[] | CredentialInstance[]> => mode === 'user'
      ? credentialsApi.listProfileInstances()
      : toolInstancesApi.list(),
  });

  // ─── Helpers ───────────────────────────────────────────────────────

  const instanceMap = useMemo(() => {
    const map = new Map<string, ToolInstance>();
    allInstances.forEach((i) => map.set(i.id, i as ToolInstance));
    return map;
  }, [allInstances]);

  const instanceOptions = useMemo(
    () => allInstances.map((i) => ({ value: i.id, label: i.name })),
    [allInstances],
  );

  const payloadFields: Record<string, string[]> = {
    token: ['token'],
    basic: ['username', 'password'],
    api_key: ['api_key'],
    litellm_api_key: ['api_key'],
    oauth: ['client_id', 'client_secret'],
  };

  const openCreate = () => {
    setSelectedInstanceId(instanceOptions[0]?.value ?? '');
    setAuthType('token');
    setPayload({ token: '' });
    setCreateOpen(true);
  };

  const createMutation = useMutation({
    mutationFn: () => credentialsApi.createProfile({
      instance_id: selectedInstanceId,
      auth_type: authType,
      payload,
    }),
    onSuccess: () => {
      showSuccess('Credential создан');
      queryClient.invalidateQueries({ queryKey: qk.profile.credentials('user') });
      setCreateOpen(false);
    },
    onError: () => showError('Не удалось создать credential'),
  });

  // ─── Mutations ─────────────────────────────────────────────────────

  const deleteMutation = useMutation({
    mutationFn: (id: string) => mode === 'user'
      ? credentialsApi.deleteProfile(id, isTenantLevel ? 'tenant' : 'user')
      : credentialsApi.delete(id),
    onSuccess: () => {
      showSuccess('Credential удалён');
      queryClient.invalidateQueries({ queryKey: qk.credentials.all() });
      if (mode === 'user') {
        queryClient.invalidateQueries({ queryKey: qk.profile.credentials(isTenantLevel ? 'tenant' : 'user') });
      }
      setConfirmDeleteId(null);
    },
    onError: () => {
      showError('Не удалось удалить credential');
    },
  });

  // ─── Table columns ────────────────────────────────────────────────

  const columns: DataTableColumn<Credential>[] = useMemo(() => [
    {
      key: 'instance_id',
      label: 'ИНСТАНС',
      render: (c: Credential) => {
        const inst = instanceMap.get(c.instance_id);
        return (
          <span style={{ fontWeight: 500 }}>
            {inst?.name || c.instance_id.slice(0, 8) + '...'}
          </span>
        );
      },
    },
    {
      key: 'auth_type',
      label: 'ТИП',
      render: (c: Credential) => (
        <Badge tone="neutral" size="small">
          {AUTH_TYPE_LABELS[c.auth_type] || c.auth_type}
        </Badge>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      render: (c: Credential) => (
        <Badge tone={c.is_active ? 'success' : 'warn'} size="small">
          {c.is_active ? 'Активен' : 'Отключен'}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      render: (c: Credential) => new Date(c.created_at).toLocaleDateString('ru-RU'),
    },
    {
      key: 'actions',
      label: '',
      render: (c: Credential) => (
        mode === 'platform' || mode === 'readonly-owner' ? null : (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setConfirmDeleteId(c.id)}
            >
              Удалить
            </Button>
          </div>
        )
      ),
    },
  ], [instanceMap, navigate, mode, isTenantLevel]);

  return (
    <div className={styles.container}>
      {/* Level switcher for user mode */}
      {mode === 'user' && tenantId && (
        <div className={styles.levelSwitcher}>
          <span className={styles.levelLabel}>Уровень:</span>
          <Badge tone={isTenantLevel ? 'neutral' : 'info'} size="small">Мои</Badge>
          <Toggle checked={isTenantLevel} onChange={setIsTenantLevel} />
          <Badge tone={isTenantLevel ? 'info' : 'neutral'} size="small">Тенант</Badge>
        </div>
      )}

      {/* Table */}
      <DataTable<Credential>
        columns={columns}
        data={credentials}
        keyField="id"
        loading={isLoading}
        emptyText="Нет credentials"
        onRowClick={mode === 'readonly-owner' || mode === 'user' ? undefined : (cred: Credential) => navigate(`/admin/credentials/${cred.id}`)}
      />

      {mode === 'user' && !isTenantLevel && (
        <Button onClick={openCreate} disabled={!instanceOptions.length}>Добавить credential</Button>
      )}

      <Modal
        open={createOpen}
        title="Добавить credential"
        onClose={() => setCreateOpen(false)}
        footer={(
          <div className={styles.formActions}>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>Отмена</Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!selectedInstanceId || Object.values(payload).some((value) => !value.trim())}
              loading={createMutation.isPending}
            >
              Сохранить
            </Button>
          </div>
        )}
      >
        <div className={styles.createForm}>
          <label className={styles.formGroup}>
            <span className={styles.formLabel}>Источник данных</span>
            <Select options={instanceOptions} value={selectedInstanceId} onChange={setSelectedInstanceId} placeholder="Выберите источник" />
          </label>
          <label className={styles.formGroup}>
            <span className={styles.formLabel}>Тип авторизации</span>
            <Select
              options={Object.entries(AUTH_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              value={authType}
              onChange={(value) => { setAuthType(value); setPayload(Object.fromEntries((payloadFields[value] ?? []).map((key) => [key, '']))); }}
            />
          </label>
          {(payloadFields[authType] ?? []).map((key) => (
            <label className={styles.formGroup} key={key}>
              <span className={styles.formLabel}>{key}</span>
              <Input
                type={key.includes('password') || key.includes('secret') || key.includes('token') || key.includes('key') ? 'password' : 'text'}
                value={payload[key] ?? ''}
                onChange={(event) => setPayload((current) => ({ ...current, [key]: event.target.value }))}
              />
            </label>
          ))}
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!confirmDeleteId}
        title="Удалить credentials?"
        message="Вы уверены, что хотите удалить эти credentials? Это действие нельзя отменить."
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={() => {
          if (confirmDeleteId) deleteMutation.mutate(confirmDeleteId);
        }}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}

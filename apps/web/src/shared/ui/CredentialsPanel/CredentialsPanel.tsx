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
import { credentialsApi, type Credential } from '@/shared/api/credentials';
import { toolInstancesApi, type ToolInstance } from '@/shared/api/toolInstances';
import { qk } from '@/shared/api/keys';
import Button from '../Button';
import Badge from '../Badge';
import Toggle from '../Toggle';
import DataTable, { type DataTableColumn } from '../DataTable/DataTable';
import ConfirmDialog from '../ConfirmDialog';
import { useErrorToast, useSuccessToast } from '../Toast';
import styles from './CredentialsPanel.module.css';

export type CredentialsPanelMode = 'platform' | 'user';

export interface CredentialsPanelProps {
  mode: CredentialsPanelMode;
  userId?: string;
  tenantId?: string;
}

const AUTH_TYPE_LABELS: Record<string, string> = {
  token: 'Bearer Token',
  basic: 'Basic Auth',
  api_key: 'API Key',
  oauth: 'OAuth 2.0',
};

export function CredentialsPanel({ mode, userId, tenantId }: CredentialsPanelProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [isTenantLevel, setIsTenantLevel] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  // ─── Queries ───────────────────────────────────────────────────────

  const listParams = useMemo(() => {
    if (mode === 'platform') {
      return { owner_platform: true };
    }
    if (isTenantLevel && tenantId) {
      return { owner_tenant_id: tenantId };
    }
    if (userId) {
      return { owner_user_id: userId };
    }
    return {};
  }, [mode, isTenantLevel, userId, tenantId]);

  const { data: credentials = [], isLoading } = useQuery({
    queryKey: qk.credentials.list(listParams),
    queryFn: () => credentialsApi.list(listParams),
  });

  const { data: allInstances = [] } = useQuery({
    queryKey: qk.toolInstances.list(),
    queryFn: () => toolInstancesApi.list(),
  });

  // ─── Helpers ───────────────────────────────────────────────────────

  const instanceMap = useMemo(() => {
    const map = new Map<string, ToolInstance>();
    allInstances.forEach((i: ToolInstance) => map.set(i.id, i));
    return map;
  }, [allInstances]);

  // ─── Mutations ─────────────────────────────────────────────────────

  const deleteMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.delete(id),
    onSuccess: () => {
      showSuccess('Credential удалён');
      queryClient.invalidateQueries({ queryKey: qk.credentials.all() });
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
        mode === 'platform' ? null : (
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
  ], [instanceMap, navigate]);

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
        onRowClick={(cred: Credential) => navigate(`/admin/credentials/${cred.id}`)}
      />

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

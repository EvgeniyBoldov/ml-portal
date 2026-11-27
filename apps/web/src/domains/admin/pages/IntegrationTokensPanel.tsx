import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { assignmentIntegrationsApi, type IntegrationToken } from '@/shared/api/assignmentIntegrations';
import { qk } from '@/shared/api/keys';
import { Badge, Button, ConfirmDialog, DataTable, FormModal, Input, Modal, type DataTableColumn } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

const fields: FieldConfig[] = [
  { key: 'name', type: 'text', label: 'Название', required: true },
  {
    key: 'days',
    type: 'custom',
    label: 'Срок действия в днях',
    render: (value: string, _editable, onChange) => (
      <Input
        type="number"
        aria-label="Срок действия в днях"
        placeholder="Без срока"
        min={1}
        max={3650}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    ),
  },
];

const date = (value: string | null) => value ? new Date(value).toLocaleString('ru-RU') : '—';

export function IntegrationTokensPanel({
  integrationId, issuing, onClose,
}: {
  integrationId: string;
  issuing: boolean;
  onClose: () => void;
}) {
  const [form, setForm] = useState({ name: '', days: '' });
  const [secret, setSecret] = useState('');
  const [toRevoke, setToRevoke] = useState<IntegrationToken | null>(null);
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const queryKey = qk.assignmentIntegrations.tokens(integrationId);
  const { data: tokens = [], isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => assignmentIntegrationsApi.tokens(integrationId),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey });
  const issue = useMutation({
    mutationFn: (data: { name: string; expires_days: number | null }) =>
      assignmentIntegrationsApi.issue(integrationId, data),
    onSuccess: (value) => {
      setSecret(value.token);
      setForm({ name: '', days: '' });
      onClose();
      void refresh();
    },
    onError: () => showError('Не удалось выпустить токен'),
  });
  const revoke = useMutation({
    mutationFn: (tokenId: string) => assignmentIntegrationsApi.revoke(integrationId, tokenId),
    onSuccess: () => {
      setToRevoke(null);
      void refresh();
    },
    onError: () => showError('Не удалось отозвать токен'),
  });
  const days = String(form.days ?? '').trim() === '' ? null : Number(form.days);
  const valid = Boolean(form.name.trim()) && (days === null || (Number.isInteger(days) && days >= 1 && days <= 3650));
  const columns: DataTableColumn<IntegrationToken>[] = [
    { key: 'name', label: 'Название' },
    { key: 'token_prefix', label: 'Токен', render: (row) => <code>{row.token_prefix}…</code> },
    {
      key: 'is_active', label: 'Статус',
      render: (row) => {
        if (!row.is_active) return <Badge tone="neutral">Отозван</Badge>;
        if (row.expires_at && Date.parse(row.expires_at) <= Date.now()) return <Badge tone="warn">Истёк</Badge>;
        return <Badge tone="success">Действует</Badge>;
      },
    },
    { key: 'created_at', label: 'Создан', render: (row) => date(row.created_at) },
    { key: 'expires_at', label: 'Действует до', render: (row) => date(row.expires_at) },
    { key: 'last_used_at', label: 'Использован', render: (row) => date(row.last_used_at) },
    {
      key: 'actions', label: '',
      render: (row) => row.is_active && <Button variant="danger" onClick={() => setToRevoke(row)}>Отозвать</Button>,
    },
  ];

  return (
    <>
      {isError && <p role="alert">Не удалось загрузить токены.</p>}
      <DataTable columns={columns} data={tokens} keyField="id" loading={isLoading} emptyText="Токены ещё не выданы." />
      <FormModal
        open={issuing}
        title="Выпустить токен"
        size="md"
        onClose={() => { if (!issue.isPending) onClose(); }}
        onSubmit={() => { if (valid) issue.mutate({ name: form.name.trim(), expires_days: days }); }}
        saving={issue.isPending}
        submitDisabled={!valid}
        submitLabel="Выпустить"
      >
        <Block
          title="Параметры токена"
          width="full"
          fields={fields}
          data={form}
          editable
          onChange={(key, value) => setForm((previous) => ({ ...previous, [key]: value }))}
        />
      </FormModal>
      <Modal
        open={Boolean(secret)}
        title="Токен выпущен"
        onClose={() => setSecret('')}
        footer={<Button onClick={() => setSecret('')}>Готово</Button>}
      >
        <p>Скопируйте токен сейчас. Он отображается только один раз.</p>
        <Input aria-label="Токен авторизации" value={secret} readOnly />
        <Button onClick={async () => {
          try {
            await navigator.clipboard.writeText(secret);
            showSuccess('Токен скопирован');
          } catch {
            showError('Не удалось скопировать токен');
          }
        }}>Скопировать</Button>
      </Modal>
      <ConfirmDialog
        open={Boolean(toRevoke)}
        title="Отозвать токен?"
        message={`Запросы с токеном «${toRevoke?.name ?? ''}» будут отклонены.`}
        confirmLabel="Отозвать"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={() => { if (toRevoke && !revoke.isPending) revoke.mutate(toRevoke.id); }}
        onCancel={() => setToRevoke(null)}
      />
    </>
  );
}

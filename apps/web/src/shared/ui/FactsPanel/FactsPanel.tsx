import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { factsApi, type Fact, type FactInput, type FactOwner } from '@/shared/api/facts';
import { qk } from '@/shared/api/keys';
import Button from '../Button';
import DataTable, { type DataTableColumn } from '../DataTable/DataTable';
import Modal from '../Modal';
import Input from '../Input';
import ConfirmDialog from '../ConfirmDialog';
import { useErrorToast, useSuccessToast } from '../Toast';
import styles from './FactsPanel.module.css';

export type FactsPanelMode = 'profile' | 'admin-user' | 'admin-tenant';

interface FactsPanelProps {
  mode: FactsPanelMode;
  ownerId?: string;
}

function FactForm({ initial, onSubmit, saving }: { initial?: Fact; onSubmit: (data: FactInput) => void; saving: boolean }) {
  const [subject, setSubject] = useState(initial?.subject ?? '');
  const [value, setValue] = useState(initial?.value ?? '');
  return (
    <div className={styles.form}>
      <label>Subject<Input value={subject} maxLength={200} onChange={(event) => setSubject(event.target.value)} /></label>
      <label>Значение<Input value={value} maxLength={500} onChange={(event) => setValue(event.target.value)} /></label>
      <Button disabled={saving || !subject.trim() || !value.trim()} onClick={() => onSubmit({ subject, value })}>
        {saving ? 'Сохранение...' : 'Сохранить'}
      </Button>
    </div>
  );
}

export function FactsPanel({ mode, ownerId }: FactsPanelProps) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const owner: FactOwner = mode === 'admin-tenant' ? 'tenant' : 'user';
  const isProfile = mode === 'profile';
  const queryKey = isProfile ? qk.profile.facts() : ownerId ? (owner === 'user' ? qk.admin.users.facts(ownerId) : qk.admin.tenants.facts(ownerId)) : qk.admin.all();
  const [editing, setEditing] = useState<Fact | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Fact | null>(null);

  const { data = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => isProfile ? factsApi.listProfile() : factsApi.listAdmin(owner, ownerId!),
    enabled: isProfile || Boolean(ownerId),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey });
  const mutation = useMutation({
    mutationFn: (input: FactInput) => editing
      ? (isProfile ? factsApi.updateProfile(editing.id, input) : factsApi.updateAdmin(owner, ownerId!, editing.id, input))
      : (isProfile ? factsApi.createProfile(input) : factsApi.createAdmin(owner, ownerId!, input)),
    onSuccess: () => { invalidate(); setEditing(null); setCreating(false); showSuccess(editing ? 'Факт обновлён' : 'Факт добавлен'); },
    onError: (error: Error) => showError(error.message || 'Не удалось сохранить факт'),
  });
  const deleteMutation = useMutation({
    mutationFn: async (fact: Fact): Promise<void> => {
      if (isProfile) {
        await factsApi.deleteProfile([fact.id]);
      } else {
        await factsApi.deleteAdmin(owner, ownerId!, fact.id);
      }
    },
    onSuccess: () => { invalidate(); setDeleting(null); showSuccess('Факт удалён'); },
    onError: (error: Error) => showError(error.message || 'Не удалось удалить факт'),
  });
  const columns: DataTableColumn<Fact>[] = [
    { key: 'subject', label: 'SUBJECT', render: (fact) => <code>{fact.subject}</code> },
    { key: 'value', label: 'ЗНАЧЕНИЕ', render: (fact) => <span className={styles.value}>{fact.value}</span> },
    { key: 'scope', label: 'SCOPE' },
    { key: 'source', label: 'ИСТОЧНИК' },
    { key: 'observed_at', label: 'ОБНОВЛЕНО', render: (fact) => new Date(fact.observed_at).toLocaleDateString('ru-RU') },
    { key: 'actions', label: '', render: (fact) => <div className={styles.actions}><Button size="sm" variant="outline" onClick={() => setEditing(fact)}>Изменить</Button><Button size="sm" variant="danger" onClick={() => setDeleting(fact)}>Удалить</Button></div> },
  ];
  return (
    <div className={styles.container}>
      <div className={styles.header}><p>Подтверждённые факты памяти</p><Button onClick={() => setCreating(true)}>Добавить факт</Button></div>
      <DataTable columns={columns} data={data} keyField="id" loading={isLoading} emptyText="Факты пока отсутствуют" />
      <Modal open={creating || Boolean(editing)} title={editing ? 'Изменить факт' : 'Добавить факт'} onClose={() => { setCreating(false); setEditing(null); }}>
        <FactForm initial={editing ?? undefined} onSubmit={(input) => mutation.mutate(input)} saving={mutation.isPending} />
      </Modal>
      <ConfirmDialog open={Boolean(deleting)} title="Удалить факт?" message={deleting?.subject ?? ''} confirmLabel="Удалить" cancelLabel="Отмена" variant="danger" onCancel={() => setDeleting(null)} onConfirm={() => deleting && deleteMutation.mutate(deleting)} />
    </div>
  );
}

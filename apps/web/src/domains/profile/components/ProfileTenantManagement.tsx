import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/shared/api/http';
import { qk } from '@/shared/api/keys';
import { MemoryScopeSelect } from '@/shared/ui/MemoryScopeSelect/MemoryScopeSelect';
import MultiSelectTagPicker from '@/shared/ui/MultiSelectTagPicker/MultiSelectTagPicker';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import Button from '@/shared/ui/Button';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './ProfileTenantManagement.module.css';

type TenantManagement = {
  tenant_id: string;
  memory_scope_keys: string[];
  data_editors: Array<{ id: string; login: string; full_name: string | null; is_data_editor: boolean }>;
};

export function ProfileTenantManagement({ tenantId }: { tenantId: string }) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const { data } = useQuery({
    queryKey: qk.profile.tenantManagement(tenantId),
    queryFn: () => apiRequest<TenantManagement>('/profile/tenant-management'),
  });
  const [editing, setEditing] = useState(false);
  const [scopeKeys, setScopeKeys] = useState<string[]>([]);
  const [editorIds, setEditorIds] = useState<string[]>([]);

  useEffect(() => {
    if (!data || editing) return;
    setScopeKeys(data.memory_scope_keys);
    setEditorIds(data.data_editors.filter(editor => editor.is_data_editor).map(editor => editor.id));
  }, [data, editing]);

  const save = useMutation({
    mutationFn: () => apiRequest('/profile/tenant-management', {
      method: 'PUT',
      body: JSON.stringify({ memory_scope_keys: scopeKeys, data_editor_user_ids: editorIds }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.profile.tenantManagement(tenantId) });
      void queryClient.invalidateQueries({ queryKey: qk.profile.all() });
      setEditing(false);
      showSuccess('Настройки рабочей группы сохранены');
    },
    onError: (error: Error) => showError(error.message),
  });

  const options = (data?.data_editors ?? []).map(user => ({
    value: user.id,
    label: user.full_name ? `${user.full_name} (${user.login})` : user.login,
  }));

  const cancelEdit = useCallback(() => {
    setScopeKeys(data?.memory_scope_keys ?? []);
    setEditorIds(data?.data_editors.filter(editor => editor.is_data_editor).map(editor => editor.id) ?? []);
    setEditing(false);
  }, [data]);

  return (
    <div className={styles.container}>
      <section className={styles.section}>
        <CredentialsPanel
          mode="tenant-admin"
          tenantId={tenantId}
          title="Учётные данные рабочей группы"
        />
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.title}>Настройки рабочей группы</h2>
            <p className={styles.description}>Настройки применяются к участникам рабочей группы вместе с их личными параметрами.</p>
          </div>
          <div className={styles.actions}>
            {editing ? (
              <>
                <Button variant="outline" onClick={cancelEdit} disabled={save.isPending}>
                  Отмена
                </Button>
                <Button onClick={() => save.mutate()} disabled={save.isPending || !data}>
                  {save.isPending ? 'Сохранение…' : 'Сохранить'}
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => setEditing(true)} disabled={!data}>
                Редактировать
              </Button>
            )}
          </div>
        </div>
        <div className={styles.settingsGrid}>
          <div className={styles.settingBlock}>
            <div>
              <h3 className={styles.blockTitle}>Редакторы данных</h3>
              <p className={styles.description}>Участники, которым разрешено добавлять и изменять данные рабочей группы.</p>
            </div>
            <MultiSelectTagPicker
              label="Редакторы данных"
              hideLabel
              options={options}
              value={editorIds}
              disabled={!editing || save.isPending || !data}
              onChange={setEditorIds}
            />
          </div>
          <div className={styles.settingBlock}>
            <div>
              <h3 className={styles.blockTitle}>Проекты для памяти чатов</h3>
              <p className={styles.description}>Проекты рабочей группы объединяются с личными проектами участника; если оба списка пусты, используется «Компания».</p>
            </div>
            <MemoryScopeSelect
              value={scopeKeys}
              onChange={setScopeKeys}
              readOnly={!editing}
              disabled={save.isPending || !data}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

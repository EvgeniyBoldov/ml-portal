import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/shared/api/http';
import { qk } from '@/shared/api/keys';
import { MemoryScopeSelect } from '@/shared/ui/MemoryScopeSelect/MemoryScopeSelect';
import MultiSelectTagPicker from '@/shared/ui/MultiSelectTagPicker/MultiSelectTagPicker';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './ProfileTenantManagement.module.css';

type TenantManagement = {
  tenant_id: string;
  memory_scope_keys: string[];
  data_editors: Array<{ id: string; login: string; full_name: string | null; is_data_editor: boolean }>;
};

export function ProfileTenantManagement({ tenantId, editRequest = 0, saveRequest = 0, cancelRequest = 0, credentialCreateRequest = 0, onEditingChange }: { tenantId: string; editRequest?: number; saveRequest?: number; cancelRequest?: number; credentialCreateRequest?: number; onEditingChange?: (editing: boolean) => void }) {
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
  const previousRequests = useRef({ editRequest, saveRequest, cancelRequest });

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
      showSuccess('Настройки тенанта сохранены');
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

  useEffect(() => {
    if (editRequest !== previousRequests.current.editRequest) {
      previousRequests.current.editRequest = editRequest;
      setEditing(true);
    }
    if (saveRequest !== previousRequests.current.saveRequest) {
      previousRequests.current.saveRequest = saveRequest;
      if (editing) save.mutate();
    }
    if (cancelRequest !== previousRequests.current.cancelRequest) {
      previousRequests.current.cancelRequest = cancelRequest;
      if (editing) cancelEdit();
    }
  }, [editRequest, saveRequest, cancelRequest, editing, save, cancelEdit]);

  useEffect(() => { onEditingChange?.(editing); }, [editing, onEditingChange]);

  return (
    <div className={styles.container}>
      <section className={styles.section}>
        <CredentialsPanel
          mode="tenant-admin"
          tenantId={tenantId}
          title="Credentials тенанта"
          createRequest={credentialCreateRequest}
          hideCreateButton
        />
      </section>

      <section className={styles.section}>
        <div>
          <h2 className={styles.title}>Редакторы данных</h2>
          <p className={styles.description}>Выберите участников, которым разрешено добавлять и изменять данные тенанта.</p>
        </div>
        <MultiSelectTagPicker
          label="Редакторы данных"
          hideLabel
          options={options}
          value={editorIds}
          disabled={!editing || save.isPending || !data}
          onChange={setEditorIds}
        />
      </section>

      <section className={styles.section}>
        <div>
          <h2 className={styles.title}>Скоупы памяти чатов</h2>
          <p className={styles.description}>Настройка применяется к участникам тенанта без личных скоупов.</p>
        </div>
        <MemoryScopeSelect
          value={scopeKeys}
          onChange={setScopeKeys}
          readOnly={!editing}
          disabled={save.isPending || !data}
        />
      </section>
    </div>
  );
}

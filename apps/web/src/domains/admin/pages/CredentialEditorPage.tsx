/**
 * CredentialEditorPage - Create/Edit credentials for tool instances
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi, toolInstancesApi, type CredentialSetCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import Alert from '@/shared/ui/Alert';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

const AUTH_TYPES = [
  { value: 'token', label: 'Bearer Token', description: 'Authorization: Bearer <token>' },
  { value: 'basic', label: 'Basic Auth', description: 'Username + Password' },
  { value: 'api_key', label: 'API Key', description: 'Custom header with API key' },
  { value: 'oauth', label: 'OAuth 2.0', description: 'OAuth client credentials' },
];

const SCOPES = [
  { value: 'tenant', label: 'Tenant', description: 'Для всех пользователей тенанта' },
  { value: 'user', label: 'User', description: 'Для конкретного пользователя' },
];

const PAYLOAD_TEMPLATES: Record<string, object> = {
  token: { token: '' },
  basic: { username: '', password: '' },
  api_key: { header_name: 'X-API-Key', api_key: '' },
  oauth: { client_id: '', client_secret: '', token_url: '' },
};

export function CredentialEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const isNew = !id || id === 'new';

  const [formData, setFormData] = useState<CredentialSetCreate>({
    tool_instance_id: '',
    scope: 'tenant',
    tenant_id: undefined,
    user_id: undefined,
    auth_type: 'token',
    encrypted_payload: {},
    is_active: true,
  });

  const [payloadText, setPayloadText] = useState(JSON.stringify(PAYLOAD_TEMPLATES.token, null, 2));

  // Load tool instances for dropdown
  const { data: toolInstances } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  // Load existing credential if editing
  const { data: existingCredential, isLoading } = useQuery({
    queryKey: qk.credentials.detail(id!),
    queryFn: () => credentialsApi.get(id!),
    enabled: !isNew,
  });

  useEffect(() => {
    if (existingCredential) {
      setFormData({
        tool_instance_id: existingCredential.tool_instance_id,
        scope: existingCredential.scope,
        tenant_id: existingCredential.tenant_id,
        user_id: existingCredential.user_id,
        auth_type: existingCredential.auth_type,
        encrypted_payload: {},
        is_active: existingCredential.is_active,
      });
      // Note: encrypted_payload is not returned from API for security
      setPayloadText(JSON.stringify(PAYLOAD_TEMPLATES[existingCredential.auth_type] || {}, null, 2));
    }
  }, [existingCredential]);

  // Update payload template when auth_type changes
  const handleAuthTypeChange = (authType: string) => {
    setFormData({ ...formData, auth_type: authType });
    setPayloadText(JSON.stringify(PAYLOAD_TEMPLATES[authType] || {}, null, 2));
  };

  const saveMutation = useMutation({
    mutationFn: (data: CredentialSetCreate) => {
      if (isNew) return credentialsApi.create(data);
      return credentialsApi.update(id!, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.credentials.all() });
      showSuccess('Credentials сохранены');
      navigate('/admin/credentials');
    },
    onError: () => {
      showError('Ошибка сохранения');
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = JSON.parse(payloadText);
      saveMutation.mutate({
        ...formData,
        encrypted_payload: payload,
        tenant_id: formData.scope === 'tenant' || formData.scope === 'user' ? formData.tenant_id : undefined,
        user_id: formData.scope === 'user' ? formData.user_id : undefined,
      });
    } catch {
      showError('Невалидный JSON в payload');
    }
  };

  if (!isNew && isLoading) {
    return <div className={styles.wrap}>Загрузка...</div>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          {isNew ? 'Создать Credentials' : 'Редактировать Credentials'}
        </h1>
        <Link to="/admin/credentials">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <Alert
        variant="warning"
        title="Безопасность"
        description="Credentials шифруются перед сохранением. При редактировании необходимо ввести данные заново."
      />

      <form onSubmit={handleSubmit} className={styles.grid} style={{ marginTop: '1rem' }}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Привязка</h2>
            <p className={styles.cardDescription}>К какому инстансу и scope</p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Tool Instance</label>
            <select
              className={styles.select}
              value={formData.tool_instance_id}
              onChange={e => setFormData({ ...formData, tool_instance_id: e.target.value })}
              required
            >
              <option value="">Выберите инстанс</option>
              {toolInstances?.map(ti => (
                <option key={ti.id} value={ti.id}>
                  {ti.tool_id.slice(0, 8)}... ({ti.scope})
                </option>
              ))}
            </select>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Scope</label>
            <select
              className={styles.select}
              value={formData.scope}
              onChange={e => setFormData({ ...formData, scope: e.target.value as 'tenant' | 'user' })}
            >
              {SCOPES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <p className={styles.description}>
              {SCOPES.find(s => s.value === formData.scope)?.description}
            </p>
          </div>

          {(formData.scope === 'tenant' || formData.scope === 'user') && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Tenant ID</label>
              <Input
                value={formData.tenant_id || ''}
                onChange={e => setFormData({ ...formData, tenant_id: e.target.value || undefined })}
                placeholder="UUID тенанта"
                required
              />
            </div>
          )}

          {formData.scope === 'user' && (
            <div className={styles.formGroup}>
              <label className={styles.label}>User ID</label>
              <Input
                value={formData.user_id || ''}
                onChange={e => setFormData({ ...formData, user_id: e.target.value || undefined })}
                placeholder="UUID пользователя"
                required
              />
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
              />
              <span>Активен</span>
            </label>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Авторизация</h2>
            <p className={styles.cardDescription}>Тип и данные для авторизации</p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Тип авторизации</label>
            <select
              className={styles.select}
              value={formData.auth_type}
              onChange={e => handleAuthTypeChange(e.target.value)}
            >
              {AUTH_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p className={styles.description}>
              {AUTH_TYPES.find(t => t.value === formData.auth_type)?.description}
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Payload (JSON)</label>
            <Textarea
              className={styles.editor}
              style={{ minHeight: '200px' }}
              value={payloadText}
              onChange={e => setPayloadText(e.target.value)}
            />
            <p className={styles.description}>
              Данные будут зашифрованы перед сохранением
            </p>
          </div>

          <div className={styles.actions}>
            <Button
              type="submit"
              variant="primary"
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

export default CredentialEditorPage;

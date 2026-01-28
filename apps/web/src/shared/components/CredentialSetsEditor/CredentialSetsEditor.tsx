/**
 * CredentialSetsEditor - Reusable component for managing credential sets
 * 
 * Used in: DefaultsPage, TenantEditorPage, UserDetailPage, ProfilePage
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi, toolInstancesApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Modal from '@/shared/ui/Modal';
import Input from '@/shared/ui/Input';
import Select from '@/shared/ui/Select';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './CredentialSetsEditor.module.css';

export type CredentialScope = 'tenant' | 'user';

interface CredentialSetsEditorProps {
  scope: CredentialScope;
  scopeId: string; // tenant_id or user_id
  title?: string;
  readOnly?: boolean;
}

interface CredentialFormData {
  instance_id: string;
  auth_type: string;
  credentials: Record<string, string>;
  is_default: boolean;
}

const AUTH_TYPES = [
  { value: 'token', label: 'API Token' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'oauth', label: 'OAuth' },
  { value: 'api_key', label: 'API Key' },
];

export function CredentialSetsEditor({ 
  scope, 
  scopeId, 
  title = 'Учётные данные',
  readOnly = false 
}: CredentialSetsEditorProps) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState<CredentialFormData>({
    instance_id: '',
    auth_type: 'token',
    credentials: {},
    is_default: false,
  });

  // Load credentials for scope
  const { data: credentials, isLoading: credentialsLoading } = useQuery({
    queryKey: qk.credentials.list({ scope, [`${scope}_id`]: scopeId }),
    queryFn: () => credentialsApi.list({ scope, [`${scope}_id`]: scopeId }),
  });

  // Load tool instances for selection
  const { data: instances } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  // Create credential
  const createMutation = useMutation({
    mutationFn: (data: CredentialFormData) => credentialsApi.create({
      ...data,
      scope,
      [`${scope}_id`]: scopeId,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.credentials.list({ scope }) });
      showSuccess('Учётные данные созданы');
      setShowCreateModal(false);
      resetForm();
    },
    onError: () => showError('Ошибка создания учётных данных'),
  });

  // Delete credential
  const deleteMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.credentials.list({ scope }) });
      showSuccess('Учётные данные удалены');
    },
    onError: () => showError('Ошибка удаления'),
  });

  // Set as default
  const setDefaultMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.update(id, { is_default: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.credentials.list({ scope }) });
      showSuccess('Установлено по умолчанию');
    },
    onError: () => showError('Ошибка обновления'),
  });

  const resetForm = () => {
    setFormData({
      instance_id: '',
      auth_type: 'token',
      credentials: {},
      is_default: false,
    });
  };

  const handleCredentialChange = (key: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      credentials: { ...prev.credentials, [key]: value },
    }));
  };

  const getCredentialFields = (authType: string) => {
    switch (authType) {
      case 'token':
        return [{ key: 'token', label: 'API Token', type: 'password' }];
      case 'basic':
        return [
          { key: 'username', label: 'Username', type: 'text' },
          { key: 'password', label: 'Password', type: 'password' },
        ];
      case 'oauth':
        return [
          { key: 'client_id', label: 'Client ID', type: 'text' },
          { key: 'client_secret', label: 'Client Secret', type: 'password' },
        ];
      case 'api_key':
        return [
          { key: 'api_key', label: 'API Key', type: 'password' },
          { key: 'header_name', label: 'Header Name', type: 'text' },
        ];
      default:
        return [];
    }
  };

  if (credentialsLoading) {
    return (
      <div className={styles.card}>
        <h3 className={styles.title}>{title}</h3>
        <Skeleton height={150} />
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h3 className={styles.title}>{title}</h3>
        {!readOnly && (
          <Button variant="outline" size="small" onClick={() => setShowCreateModal(true)}>
            + Добавить
          </Button>
        )}
      </div>

      {credentials && credentials.length > 0 ? (
        <div className={styles.list}>
          {credentials.map((cred: any) => {
            const instance = instances?.find((i: any) => i.id === cred.instance_id);
            return (
              <div key={cred.id} className={styles.item}>
                <div className={styles.itemInfo}>
                  <div className={styles.itemHeader}>
                    <span className={styles.itemName}>
                      {instance?.tool?.name || 'Unknown Tool'}
                    </span>
                    {cred.is_default && (
                      <Badge variant="success" size="small">По умолчанию</Badge>
                    )}
                  </div>
                  <div className={styles.itemMeta}>
                    <Badge variant="secondary" size="small">{cred.auth_type}</Badge>
                    <code className={styles.instanceId}>{cred.instance_id.slice(0, 8)}...</code>
                  </div>
                </div>
                {!readOnly && (
                  <div className={styles.itemActions}>
                    {!cred.is_default && (
                      <Button 
                        variant="ghost" 
                        size="small"
                        onClick={() => setDefaultMutation.mutate(cred.id)}
                        disabled={setDefaultMutation.isPending}
                      >
                        По умолчанию
                      </Button>
                    )}
                    <Button 
                      variant="ghost" 
                      size="small"
                      onClick={() => deleteMutation.mutate(cred.id)}
                      disabled={deleteMutation.isPending}
                    >
                      Удалить
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className={styles.empty}>Нет учётных данных</p>
      )}

      {/* Create Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => { setShowCreateModal(false); resetForm(); }}
        title="Добавить учётные данные"
      >
        <div className={styles.form}>
          <div className={styles.formGroup}>
            <label>Инстанс инструмента</label>
            <Select
              value={formData.instance_id}
              onChange={(e) => setFormData(prev => ({ ...prev, instance_id: e.target.value }))}
              options={[
                { value: '', label: 'Выберите инстанс' },
                ...(instances?.map((i: any) => ({
                  value: i.id,
                  label: `${i.tool?.name || 'Unknown'} (${i.id.slice(0, 8)}...)`,
                })) || []),
              ]}
            />
          </div>

          <div className={styles.formGroup}>
            <label>Тип авторизации</label>
            <Select
              value={formData.auth_type}
              onChange={(e) => setFormData(prev => ({ 
                ...prev, 
                auth_type: e.target.value,
                credentials: {},
              }))}
              options={AUTH_TYPES}
            />
          </div>

          {getCredentialFields(formData.auth_type).map(field => (
            <div key={field.key} className={styles.formGroup}>
              <label>{field.label}</label>
              <Input
                type={field.type}
                value={formData.credentials[field.key] || ''}
                onChange={(e) => handleCredentialChange(field.key, e.target.value)}
              />
            </div>
          ))}

          <div className={styles.formActions}>
            <Button variant="outline" onClick={() => { setShowCreateModal(false); resetForm(); }}>
              Отмена
            </Button>
            <Button 
              variant="primary"
              onClick={() => createMutation.mutate(formData)}
              disabled={createMutation.isPending || !formData.instance_id}
            >
              {createMutation.isPending ? 'Создание...' : 'Создать'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default CredentialSetsEditor;

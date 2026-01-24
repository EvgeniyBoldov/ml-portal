/**
 * ProfilePage - Личный кабинет пользователя
 * Управление профилем и API токенами для MCP/IDE
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@shared/api/http';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import Modal from '@shared/ui/Modal';
import ConfirmDialog from '@shared/ui/ConfirmDialog';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import styles from './ProfilePage.module.css';

interface Profile {
  id: string;
  login: string;
  email: string | null;
  role: string;
  created_at: string;
  tenants: string[];
}

interface ApiToken {
  id: string;
  name: string;
  token_prefix: string;
  scopes: string | null;
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

interface ApiTokenCreated extends ApiToken {
  token: string;
}

interface UserCredential {
  id: string;
  tool_instance_id: string;
  tool_name?: string;
  auth_type: string;
  is_active: boolean;
  created_at: string;
}

interface ToolInstance {
  id: string;
  tool_id: string;
  tool?: { name: string; slug: string };
  is_active: boolean;
}

const formatDate = (dateString: string | null) => {
  if (!dateString) return '—';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatRelativeDate = (dateString: string | null) => {
  if (!dateString) return null;
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return null;
  
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
  
  if (days < 0) return 'Истёк';
  if (days === 0) return 'Сегодня';
  if (days === 1) return 'Завтра';
  if (days < 7) return `${days} дн.`;
  if (days < 30) return `${Math.ceil(days / 7)} нед.`;
  return `${Math.ceil(days / 30)} мес.`;
};

const getRoleLabel = (role: string) => {
  switch (role) {
    case 'admin': return 'Администратор';
    case 'editor': return 'Редактор';
    case 'reader': return 'Читатель';
    default: return role;
  }
};

const EXPIRATION_OPTIONS = [
  { value: '', label: 'Без срока действия' },
  { value: '7', label: '7 дней' },
  { value: '30', label: '30 дней' },
  { value: '90', label: '90 дней' },
  { value: '365', label: '1 год' },
];

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTokenName, setNewTokenName] = useState('');
  const [expiresDays, setExpiresDays] = useState('');
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [tokenToDelete, setTokenToDelete] = useState<ApiToken | null>(null);
  const [showCredentialModal, setShowCredentialModal] = useState(false);
  const [selectedInstance, setSelectedInstance] = useState('');
  const [credAuthType, setCredAuthType] = useState('token');
  const [credPayload, setCredPayload] = useState('');
  const [credToDelete, setCredToDelete] = useState<UserCredential | null>(null);

  // Fetch profile
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest<Profile>('/profile/me'),
  });

  // Fetch tokens
  const { data: tokens = [], isLoading: tokensLoading } = useQuery({
    queryKey: ['profile', 'tokens'],
    queryFn: () => apiRequest<ApiToken[]>('/profile/tokens'),
  });

  // Fetch user credentials
  const { data: credentials = [], isLoading: credentialsLoading } = useQuery({
    queryKey: ['profile', 'credentials'],
    queryFn: () => apiRequest<UserCredential[]>('/profile/credentials'),
  });

  // Fetch available tool instances
  const { data: instances = [] } = useQuery({
    queryKey: ['tool-instances', 'active'],
    queryFn: () => apiRequest<ToolInstance[]>('/api/v1/admin/tool-instances?is_active=true'),
  });

  // Create token mutation
  const createToken = useMutation({
    mutationFn: async (data: { name: string; expires_days?: number }) => {
      const result = await apiRequest<ApiTokenCreated>('/profile/tokens', {
        method: 'POST',
        body: JSON.stringify({ 
          name: data.name, 
          scopes: 'mcp,chat,rag',
          expires_days: data.expires_days || null,
        }),
      });
      return result;
    },
    onSuccess: (data) => {
      setCreatedToken(data.token);
      setNewTokenName('');
      setExpiresDays('');
      queryClient.invalidateQueries({ queryKey: ['profile', 'tokens'] });
      showSuccess('Токен создан');
    },
    onError: (error: any) => {
      showError(error?.detail || 'Не удалось создать токен');
    },
  });

  // Delete token mutation
  const deleteToken = useMutation({
    mutationFn: (tokenId: string) => 
      apiRequest(`/profile/tokens/${tokenId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', 'tokens'] });
      showSuccess('Токен удалён');
      setTokenToDelete(null);
    },
    onError: () => {
      showError('Не удалось удалить токен');
    },
  });

  // Create credential mutation
  const createCredential = useMutation({
    mutationFn: async (data: { tool_instance_id: string; auth_type: string; payload: string }) => {
      return apiRequest('/profile/credentials', {
        method: 'POST',
        body: JSON.stringify({
          tool_instance_id: data.tool_instance_id,
          auth_type: data.auth_type,
          encrypted_payload: JSON.parse(data.payload),
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', 'credentials'] });
      showSuccess('Credentials сохранены');
      handleCloseCredentialModal();
    },
    onError: () => {
      showError('Не удалось сохранить credentials');
    },
  });

  // Delete credential mutation
  const deleteCredential = useMutation({
    mutationFn: (credId: string) => 
      apiRequest(`/profile/credentials/${credId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', 'credentials'] });
      showSuccess('Credentials удалены');
      setCredToDelete(null);
    },
    onError: () => {
      showError('Не удалось удалить credentials');
    },
  });

  const handleCreateToken = () => {
    if (!newTokenName.trim()) return;
    createToken.mutate({
      name: newTokenName.trim(),
      expires_days: expiresDays ? parseInt(expiresDays) : undefined,
    });
  };

  const handleCopyToken = async () => {
    if (!createdToken) return;
    try {
      await navigator.clipboard.writeText(createdToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showError('Не удалось скопировать');
    }
  };

  const handleCloseModal = () => {
    setShowCreateModal(false);
    setCreatedToken(null);
    setNewTokenName('');
    setExpiresDays('');
    setCopied(false);
  };

  const handleCloseCredentialModal = () => {
    setShowCredentialModal(false);
    setSelectedInstance('');
    setCredAuthType('token');
    setCredPayload('');
  };

  const handleCreateCredential = () => {
    if (!selectedInstance || !credPayload.trim()) return;
    try {
      JSON.parse(credPayload);
      createCredential.mutate({
        tool_instance_id: selectedInstance,
        auth_type: credAuthType,
        payload: credPayload,
      });
    } catch {
      showError('Невалидный JSON');
    }
  };

  const getPayloadTemplate = (authType: string) => {
    switch (authType) {
      case 'token': return JSON.stringify({ token: '' }, null, 2);
      case 'basic': return JSON.stringify({ username: '', password: '' }, null, 2);
      case 'api_key': return JSON.stringify({ header_name: 'X-API-Key', api_key: '' }, null, 2);
      case 'oauth': return JSON.stringify({ client_id: '', client_secret: '', token_url: '' }, null, 2);
      default: return '{}';
    }
  };

  if (profileLoading) {
    return <div className={styles.loading}>Загрузка...</div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Личный кабинет</h1>
      </div>

      {/* Profile Section */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
          Профиль
        </h2>
        
        {profile && (
          <div className={styles.profileGrid}>
            <div className={styles.profileItem}>
              <span className={styles.profileLabel}>Логин</span>
              <span className={styles.profileValue}>{profile.login}</span>
            </div>
            <div className={styles.profileItem}>
              <span className={styles.profileLabel}>Email</span>
              <span className={styles.profileValue}>{profile.email || '—'}</span>
            </div>
            <div className={styles.profileItem}>
              <span className={styles.profileLabel}>Роль</span>
              <span className={styles.profileValue}>{getRoleLabel(profile.role)}</span>
            </div>
            <div className={styles.profileItem}>
              <span className={styles.profileLabel}>Дата регистрации</span>
              <span className={styles.profileValue}>{formatDate(profile.created_at)}</span>
            </div>
          </div>
        )}
      </section>

      {/* API Tokens Section */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            API Токены
          </h2>
          <Button onClick={() => setShowCreateModal(true)}>
            + Создать токен
          </Button>
        </div>

        <p className={styles.sectionDescription}>
          Токены используются для доступа к API из IDE плагинов и внешних приложений (MCP).
          Храните токены в безопасности — они дают полный доступ к вашему аккаунту.
        </p>

        {tokensLoading ? (
          <div className={styles.loading}>Загрузка токенов...</div>
        ) : tokens.length === 0 ? (
          <div className={styles.emptyState}>
            <p>У вас пока нет API токенов</p>
            <Button onClick={() => setShowCreateModal(true)}>
              Создать первый токен
            </Button>
          </div>
        ) : (
          <div className={styles.tokensList}>
            {tokens.map(token => {
              const expiresLabel = formatRelativeDate(token.expires_at);
              const isExpired = expiresLabel === 'Истёк';
              
              return (
                <div key={token.id} className={`${styles.tokenCard} ${isExpired ? styles.tokenExpired : ''}`}>
                  <div className={styles.tokenInfo}>
                    <div className={styles.tokenHeader}>
                      <span className={styles.tokenName}>{token.name}</span>
                      {expiresLabel && (
                        <span className={`${styles.tokenBadge} ${isExpired ? styles.expired : ''}`}>
                          {isExpired ? '⚠️ Истёк' : `⏱ ${expiresLabel}`}
                        </span>
                      )}
                    </div>
                    <div className={styles.tokenMeta}>
                      <span className={styles.tokenPrefix}>{token.token_prefix}...</span>
                      <span className={styles.tokenDate}>
                        Создан: {formatDate(token.created_at)}
                      </span>
                      {token.last_used_at && (
                        <span className={styles.tokenDate}>
                          Использован: {formatDate(token.last_used_at)}
                        </span>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="danger"
                    onClick={() => setTokenToDelete(token)}
                    disabled={deleteToken.isPending}
                  >
                    Удалить
                  </Button>
                </div>
              );
            })}
          </div>
        )}

        {/* Usage Instructions */}
        <div className={styles.usageSection}>
          <h3 className={styles.usageTitle}>Как использовать токен</h3>
          <div className={styles.usageCode}>
            <code>
              curl -H "X-API-Key: YOUR_TOKEN" \<br />
              &nbsp;&nbsp;https://your-server/api/v1/mcp
            </code>
          </div>
          <p className={styles.usageHint}>
            Используйте токен в заголовке <code>X-API-Key</code> для авторизации запросов к MCP API.
          </p>
        </div>
      </section>

      {/* Credentials Section */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
            </svg>
            Мои Credentials
          </h2>
          <Button onClick={() => {
            setCredPayload(getPayloadTemplate('token'));
            setShowCredentialModal(true);
          }}>
            + Добавить credentials
          </Button>
        </div>

        <p className={styles.sectionDescription}>
          Ваши персональные учётные данные для подключения к инструментам. 
          Credentials шифруются и используются при выполнении запросов.
        </p>

        {credentialsLoading ? (
          <div className={styles.loading}>Загрузка credentials...</div>
        ) : credentials.length === 0 ? (
          <div className={styles.emptyState}>
            <p>У вас пока нет сохранённых credentials</p>
            <Button onClick={() => {
              setCredPayload(getPayloadTemplate('token'));
              setShowCredentialModal(true);
            }}>
              Добавить credentials
            </Button>
          </div>
        ) : (
          <div className={styles.tokensList}>
            {credentials.map(cred => (
              <div key={cred.id} className={styles.tokenCard}>
                <div className={styles.tokenInfo}>
                  <div className={styles.tokenHeader}>
                    <span className={styles.tokenName}>
                      {cred.tool_name || cred.tool_instance_id.slice(0, 8) + '...'}
                    </span>
                    <span className={styles.tokenBadge}>{cred.auth_type}</span>
                  </div>
                  <div className={styles.tokenMeta}>
                    <span className={styles.tokenDate}>
                      Создан: {formatDate(cred.created_at)}
                    </span>
                  </div>
                </div>
                <Button
                  variant="danger"
                  onClick={() => setCredToDelete(cred)}
                  disabled={deleteCredential.isPending}
                >
                  Удалить
                </Button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Delete Token Confirmation */}
      <ConfirmDialog
        open={!!tokenToDelete}
        title="Удалить токен?"
        message={tokenToDelete ? `Вы уверены, что хотите удалить токен "${tokenToDelete.name}"? Это действие нельзя отменить.` : ''}
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={() => {
          if (tokenToDelete) {
            deleteToken.mutate(tokenToDelete.id);
          }
        }}
        onCancel={() => setTokenToDelete(null)}
      />

      {/* Delete Credential Confirmation */}
      <ConfirmDialog
        open={!!credToDelete}
        title="Удалить credentials?"
        message={credToDelete ? `Вы уверены, что хотите удалить credentials для "${credToDelete.tool_name || 'инструмента'}"? Это действие нельзя отменить.` : ''}
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={() => {
          if (credToDelete) {
            deleteCredential.mutate(credToDelete.id);
          }
        }}
        onCancel={() => setCredToDelete(null)}
      />

      {/* Create Token Modal */}
      <Modal 
        open={showCreateModal} 
        onClose={handleCloseModal} 
        title={createdToken ? 'Токен создан' : 'Создать токен'}
      >
        {createdToken ? (
            <div className={styles.tokenCreated}>
              <p className={styles.tokenWarning}>
                ⚠️ Скопируйте токен сейчас. Он больше не будет показан!
              </p>
              <div className={styles.tokenDisplay}>
                <code className={styles.tokenCode}>{createdToken}</code>
                <Button onClick={handleCopyToken}>
                  {copied ? '✓ Скопировано' : 'Копировать'}
                </Button>
              </div>
              <div className={styles.modalActions}>
                <Button onClick={handleCloseModal}>Готово</Button>
              </div>
            </div>
          ) : (
            <div className={styles.createForm}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Название токена</label>
                <Input
                  value={newTokenName}
                  onChange={e => setNewTokenName(e.target.value)}
                  placeholder="Например: VS Code Plugin"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newTokenName.trim()) {
                      e.preventDefault();
                      handleCreateToken();
                    }
                  }}
                />
                <span className={styles.formHelp}>
                  Название поможет вам отличать токены друг от друга
                </span>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Срок действия</label>
                <Select
                  value={expiresDays}
                  onChange={e => setExpiresDays(e.target.value)}
                >
                  {EXPIRATION_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <span className={styles.formHelp}>
                  Рекомендуем устанавливать срок действия для безопасности
                </span>
              </div>
              <div className={styles.modalActions}>
                <Button variant="outline" onClick={handleCloseModal}>
                  Отмена
                </Button>
                <Button 
                  onClick={handleCreateToken}
                  disabled={!newTokenName.trim() || createToken.isPending}
                >
                  {createToken.isPending ? 'Создание...' : 'Создать'}
                </Button>
              </div>
            </div>
          )}
      </Modal>

      {/* Create Credential Modal */}
      <Modal 
        open={showCredentialModal} 
        onClose={handleCloseCredentialModal} 
        title="Добавить credentials"
      >
        <div className={styles.createForm}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Инструмент</label>
            <Select
              value={selectedInstance}
              onChange={e => setSelectedInstance(e.target.value)}
            >
              <option value="">Выберите инструмент</option>
              {instances.map(inst => (
                <option key={inst.id} value={inst.id}>
                  {inst.tool?.name || inst.tool_id.slice(0, 8)}
                </option>
              ))}
            </Select>
            <span className={styles.formHelp}>
              Инструмент, для которого добавляются credentials
            </span>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Тип авторизации</label>
            <Select
              value={credAuthType}
              onChange={e => {
                setCredAuthType(e.target.value);
                setCredPayload(getPayloadTemplate(e.target.value));
              }}
            >
              <option value="token">Bearer Token</option>
              <option value="basic">Basic Auth</option>
              <option value="api_key">API Key</option>
              <option value="oauth">OAuth 2.0</option>
            </Select>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Данные (JSON)</label>
            <textarea
              className={styles.codeInput}
              value={credPayload}
              onChange={e => setCredPayload(e.target.value)}
              rows={6}
              style={{ fontFamily: 'monospace', width: '100%', padding: '0.5rem' }}
            />
            <span className={styles.formHelp}>
              Данные будут зашифрованы перед сохранением
            </span>
          </div>
          <div className={styles.modalActions}>
            <Button variant="outline" onClick={handleCloseCredentialModal}>
              Отмена
            </Button>
            <Button 
              onClick={handleCreateCredential}
              disabled={!selectedInstance || !credPayload.trim() || createCredential.isPending}
            >
              {createCredential.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

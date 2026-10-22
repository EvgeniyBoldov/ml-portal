/**
 * ProfilePage - Личный кабинет пользователя
 * Управление профилем и персональными API токенами
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@shared/api/http';
import { qk } from '@/shared/api/keys';
import { ProfileMemoryScopes } from '../components/ProfileMemoryScopes';
import { ProfileTenantManagement } from '../components/ProfileTenantManagement';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import Modal from '@shared/ui/Modal';
import ConfirmDialog from '@shared/ui/ConfirmDialog';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { CredentialsPanel } from '@/shared/ui/CredentialsPanel';
import { FactsPanel } from '@/shared/ui/FactsPanel/FactsPanel';
import styles from './ProfilePage.module.css';

interface Profile {
  id: string;
  login: string;
  email: string | null;
  role: string;
  auth_provider: string;
  is_admin: boolean;
  is_tenant_admin: boolean;
  created_at: string;
  tenants: string[];
  memory_scope_keys: string[];
  tenant_memory_scope_keys: string[];
}

interface ApiToken {
  id: string;
  name: string;
  token_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

interface ApiTokenCreated extends ApiToken {
  token: string;
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
    case 'admin':
      return 'Администратор';
    case 'editor':
      return 'Редактор';
    case 'tenant_admin':
      return 'Администратор тенанта';
    case 'reader':
      return 'Читатель';
    default:
      return role;
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
  const apiBaseUrl = `${window.location.origin}/api/v1`;
  const shadowExample = [
    `curl --request POST '${apiBaseUrl}/agents/shadow/invoke' \\`,
    '  --header "Authorization: Bearer YOUR_TOKEN" \\',
    '  --header "Content-Type: application/json" \\',
    '  --data \'{"agent":"YOUR_SHADOW_AGENT","data":{}}\'',
  ].join('\n');
  const mcpExample = [
    `curl --request POST '${apiBaseUrl}/mcp' \\`,
    '  --header "Authorization: Bearer YOUR_TOKEN" \\',
    '  --header "Content-Type: application/json" \\',
    '  --data \'{"jsonrpc":"2.0","id":1,"method":"ping"}\'',
  ].join('\n');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTokenName, setNewTokenName] = useState('');
  const [expiresDays, setExpiresDays] = useState('');
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [tokenToDelete, setTokenToDelete] = useState<ApiToken | null>(null);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [revealPassword, setRevealPassword] = useState(false);
  const [activeTab, setActiveTab] = useState<'info' | 'credentials' | 'tenant-management' | 'facts'>(
    'info'
  );
  const [editingScopes, setEditingScopes] = useState(false);
  const [scopeDraft, setScopeDraft] = useState<string[]>([]);
  const [credentialCreateRequest, setCredentialCreateRequest] = useState(0);
  const [factCreateRequest, setFactCreateRequest] = useState(0);
  const [tenantCredentialCreateRequest, setTenantCredentialCreateRequest] = useState(0);
  const [tenantEditRequest, setTenantEditRequest] = useState(0);
  const [tenantSaveRequest, setTenantSaveRequest] = useState(0);
  const [tenantCancelRequest, setTenantCancelRequest] = useState(0);
  const [tenantEditing, setTenantEditing] = useState(false);

  // Fetch profile
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: qk.profile.detail(),
    queryFn: () => apiRequest<Profile>('/profile/me'),
  });

  // Fetch tokens
  const { data: tokens = [], isLoading: tokensLoading } = useQuery({
    queryKey: qk.profile.tokens(),
    queryFn: async () => {
      const result = await apiRequest<unknown>('/profile/tokens');
      if (!Array.isArray(result)) {
        throw new Error('Некорректный формат ответа API токенов');
      }
      return result as ApiToken[];
    },
  });

  // Create token mutation
  const createToken = useMutation({
    mutationFn: async (data: { name: string; expires_days?: number }) => {
      const result = await apiRequest<ApiTokenCreated>('/profile/tokens', {
        method: 'POST',
        body: JSON.stringify({
          name: data.name,
          expires_days: data.expires_days || null,
        }),
      });
      return result;
    },
    onSuccess: data => {
      setCreatedToken(data.token);
      setNewTokenName('');
      setExpiresDays('');
      queryClient.invalidateQueries({ queryKey: qk.profile.tokens() });
      showSuccess('Токен создан');
    },
    onError: (error: unknown) => {
      showError(
        error instanceof Error ? error.message : 'Не удалось создать токен'
      );
    },
  });

  // Delete token mutation
  const deleteToken = useMutation({
    mutationFn: (tokenId: string) =>
      apiRequest(`/profile/tokens/${tokenId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.profile.tokens() });
      showSuccess('Токен удалён');
      setTokenToDelete(null);
    },
    onError: () => {
      showError('Не удалось удалить токен');
    },
  });

  const changePassword = useMutation({
    mutationFn: async (data: {
      current_password: string;
      new_password: string;
    }) => {
      return apiRequest<{ ok: boolean }>('/profile/password', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      showSuccess('Пароль обновлён');
      setShowPasswordModal(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setRevealPassword(false);
    },
    onError: (error: unknown) => {
      const detail = error instanceof Error ? error.message : '';
      if (String(detail).includes('invalid_current_password')) {
        showError('Текущий пароль указан неверно');
        return;
      }
      if (String(detail).includes('password_too_short')) {
        showError('Новый пароль должен быть не короче 8 символов');
        return;
      }
      showError('Не удалось сменить пароль');
    },
  });

  const saveScopes = useMutation({
    mutationFn: () => apiRequest('/profile/memory-scopes', {
      method: 'PUT', body: JSON.stringify({ memory_scope_keys: scopeDraft }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.profile.all() });
      void queryClient.invalidateQueries({ queryKey: qk.chats.all() });
      setEditingScopes(false);
      showSuccess('Личные скоупы сохранены');
    },
    onError: (error: Error) => showError(error.message),
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
      await window.navigator.clipboard.writeText(createdToken);
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

  const handleChangePassword = () => {
    if (!currentPassword.trim()) {
      showError('Введите текущий пароль');
      return;
    }
    if (newPassword.length < 8) {
      showError('Новый пароль должен быть не короче 8 символов');
      return;
    }
    if (newPassword !== confirmPassword) {
      showError('Новые пароли не совпадают');
      return;
    }
    changePassword.mutate({
      current_password: currentPassword,
      new_password: newPassword,
    });
  };

  const startScopeEdit = () => {
    setScopeDraft(profile?.memory_scope_keys ?? []);
    setEditingScopes(true);
  };

  const cancelScopeEdit = () => {
    setScopeDraft(profile?.memory_scope_keys ?? []);
    setEditingScopes(false);
  };

  const selectTab = (tab: 'info' | 'credentials' | 'tenant-management' | 'facts') => {
    setEditingScopes(false);
    setTenantEditing(false);
    setActiveTab(tab);
  };

  if (profileLoading) {
    return <div className={styles.loading}>Загрузка...</div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Личный кабинет</h1>
        <div className={styles.headerActions}>
          {activeTab === 'info' && <>
            {editingScopes ? <>
              <Button variant="outline" onClick={cancelScopeEdit} disabled={saveScopes.isPending}>Отмена</Button>
              <Button variant="primary" onClick={() => saveScopes.mutate()} disabled={saveScopes.isPending}>{saveScopes.isPending ? 'Сохранение…' : 'Сохранить'}</Button>
            </> : <Button variant="primary" onClick={startScopeEdit}>Редактировать</Button>}
            {profile?.auth_provider === 'local' && <Button variant="outline" onClick={() => setShowPasswordModal(true)}>Сменить пароль</Button>}
          </>}
          {activeTab === 'credentials' && <>
            <Button variant="primary" onClick={() => setCredentialCreateRequest(value => value + 1)}>Добавить credential</Button>
            <Button variant="primary" onClick={() => setShowCreateModal(true)}>Создать токен</Button>
          </>}
          {activeTab === 'tenant-management' && profile?.is_tenant_admin && <>
            <Button variant="primary" onClick={() => setTenantCredentialCreateRequest(value => value + 1)}>Добавить credential</Button>
            {tenantEditing ? <>
              <Button variant="outline" onClick={() => setTenantCancelRequest(value => value + 1)}>Отмена</Button>
              <Button variant="primary" onClick={() => setTenantSaveRequest(value => value + 1)}>Сохранить</Button>
            </> : <Button variant="primary" onClick={() => setTenantEditRequest(value => value + 1)}>Редактировать</Button>}
          </>}
          {activeTab === 'facts' && <Button onClick={() => setFactCreateRequest(value => value + 1)}>Добавить факт</Button>}
        </div>
      </div>

      <nav className={styles.tabs} aria-label="Разделы личного кабинета">
        <button
          className={activeTab === 'info' ? styles.activeTab : styles.tab}
          onClick={() => selectTab('info')}
          type="button"
        >
          Информация
        </button>
        <button
          className={
            activeTab === 'credentials' ? styles.activeTab : styles.tab
          }
          onClick={() => selectTab('credentials')}
          type="button"
        >
          Credentials
        </button>
        {profile?.is_tenant_admin && <button
          className={activeTab === 'tenant-management' ? styles.activeTab : styles.tab}
          onClick={() => selectTab('tenant-management')}
          type="button"
        >Управление тенантом</button>}
        <button
          className={activeTab === 'facts' ? styles.activeTab : styles.tab}
          onClick={() => selectTab('facts')}
          type="button"
        >
          Факты
        </button>
      </nav>

      {/* Profile Section */}
      {activeTab === 'info' && (
        <>
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
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
                  <span className={styles.profileValue}>
                    {profile.email || '—'}
                  </span>
                </div>
                <div className={styles.profileItem}>
                  <span className={styles.profileLabel}>Роль</span>
                  <span className={styles.profileValue}>
                    {getRoleLabel(profile.role)}
                  </span>
                </div>
                <div className={styles.profileItem}>
                  <span className={styles.profileLabel}>Дата регистрации</span>
                  <span className={styles.profileValue}>
                    {formatDate(profile.created_at)}
                  </span>
                </div>
              </div>
            )}
          </section>

          {profile && (
            <section className={styles.section}>
              <ProfileMemoryScopes
                scopeKeys={profile.memory_scope_keys ?? []}
                tenantScopeKeys={profile.tenant_memory_scope_keys ?? []}
                hasTenant={Boolean(profile.tenants?.length)}
                editable={editingScopes}
                onChange={setScopeDraft}
              />
            </section>
          )}
        </>
      )}

      {/* Credentials Section */}
      {activeTab === 'credentials' && (
        <>
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
              </svg>
              Мои Credentials
            </h2>
            <p className={styles.sectionDescription}>
              Ваши персональные учётные данные для подключения к инструментам.
              Credentials шифруются и используются при выполнении запросов.
            </p>
            <CredentialsPanel
              mode="user"
              userId={profile?.id}
              tenantId={profile?.tenants?.[0]}
              createRequest={credentialCreateRequest}
              hideCreateButton
            />
          </section>
        </>
      )}

      {/* API Tokens Section */}
      {activeTab === 'credentials' && (
        <>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                API Токены
              </h2>
            </div>

            <p className={styles.sectionDescription}>
              Персональные токены используются для вызова API, shadow-агентов и
              MCP из внешних приложений. Запросы выполняются с вашими
              действующими правами. Храните токены в безопасности — полный токен
              показывается только при создании. Удаление токена сразу прекращает
              его действие.
            </p>

            {tokensLoading ? (
              <div className={styles.loading}>Загрузка токенов...</div>
            ) : tokens.length === 0 ? (
              <div className={styles.emptyState}>
                <p>У вас пока нет API токенов</p>
              </div>
            ) : (
              <div className={styles.tokensList}>
                {tokens.map(token => {
                  const expiresLabel = formatRelativeDate(token.expires_at);
                  const isExpired = expiresLabel === 'Истёк';

                  return (
                    <div
                      key={token.id}
                      className={`${styles.tokenCard} ${isExpired ? styles.tokenExpired : ''}`}
                    >
                      <div className={styles.tokenInfo}>
                        <div className={styles.tokenHeader}>
                          <span className={styles.tokenName}>{token.name}</span>
                          {expiresLabel && (
                            <span
                              className={`${styles.tokenBadge} ${isExpired ? styles.expired : ''}`}
                            >
                              {isExpired ? '⚠️ Истёк' : `⏱ ${expiresLabel}`}
                            </span>
                          )}
                        </div>
                        <div className={styles.tokenMeta}>
                          <span className={styles.tokenPrefix}>
                            {token.token_prefix}...
                          </span>
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
              <p className={styles.usageHint}>Вызов shadow-агента</p>
              <div className={styles.usageCode}>
                <pre>
                  <code>{shadowExample}</code>
                </pre>
              </div>
              <p className={styles.usageHint}>Проверка подключения к MCP</p>
              <div className={styles.usageCode}>
                <pre>
                  <code>{mcpExample}</code>
                </pre>
              </div>
              <p className={styles.usageHint}>
                Замените <code>YOUR_TOKEN</code> на созданный токен, а{' '}
                <code>YOUR_SHADOW_AGENT</code> — на slug доступного вам
                shadow-агента. Передавайте токен в заголовке{' '}
                <code>Authorization: Bearer YOUR_TOKEN</code>. Тот же заголовок
                используется для JWT access token.
              </p>
            </div>
          </section>
        </>
      )}

      {activeTab === 'tenant-management' && profile?.is_tenant_admin && profile.tenants?.[0] && (
        <ProfileTenantManagement
          tenantId={profile.tenants[0]}
          editRequest={tenantEditRequest}
          saveRequest={tenantSaveRequest}
          cancelRequest={tenantCancelRequest}
          credentialCreateRequest={tenantCredentialCreateRequest}
          onEditingChange={setTenantEditing}
        />
      )}

      {/* Facts Section */}
      {activeTab === 'facts' && (
        <>
          <FactsPanel mode="profile" createRequest={factCreateRequest} hideCreateButton />
        </>
      )}

      {/* Delete Token Confirmation */}
      <ConfirmDialog
        open={!!tokenToDelete}
        title="Удалить токен?"
        message={
          tokenToDelete
            ? `Вы уверены, что хотите удалить токен "${tokenToDelete.name}"? Это действие нельзя отменить.`
            : ''
        }
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
                onKeyDown={e => {
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
                onChange={value => setExpiresDays(value)}
                options={EXPIRATION_OPTIONS}
              />
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

      <Modal
        open={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        title="Сменить пароль"
      >
        <div className={styles.createForm}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Текущий пароль</label>
            <Input
              type={revealPassword ? 'text' : 'password'}
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Новый пароль</label>
            <Input
              type={revealPassword ? 'text' : 'password'}
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Повторите новый пароль</label>
            <Input
              type={revealPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div
            className={styles.modalActions}
            style={{
              justifyContent: 'flex-start',
              borderTop: 'none',
              paddingTop: 0,
            }}
          >
            <Button
              variant="ghost"
              onClick={() => setRevealPassword(v => !v)}
              type="button"
            >
              {revealPassword ? 'Скрыть пароль' : 'Показать пароль'}
            </Button>
          </div>
          <div className={styles.modalActions}>
            <Button
              variant="outline"
              onClick={() => setShowPasswordModal(false)}
            >
              Отмена
            </Button>
            <Button
              onClick={handleChangePassword}
              disabled={changePassword.isPending}
            >
              {changePassword.isPending ? 'Сохранение...' : 'Сменить пароль'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

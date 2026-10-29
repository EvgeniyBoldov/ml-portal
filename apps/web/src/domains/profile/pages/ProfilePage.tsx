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

type PasswordErrors = Partial<
  Record<'current' | 'new' | 'confirm' | 'form', string>
>;

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
  if (diff < 0) return 'Истёк';
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));

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
      return 'Администратор рабочей группы';
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
  const [passwordErrors, setPasswordErrors] = useState<PasswordErrors>({});
  const [activeTab, setActiveTab] = useState<
    'info' | 'credentials' | 'tenant-management' | 'facts'
  >('info');
  const [editingScopes, setEditingScopes] = useState(false);
  const [scopeDraft, setScopeDraft] = useState<string[]>([]);

  // Fetch profile
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: qk.profile.detail(),
    queryFn: () => apiRequest<Profile>('/profile/me'),
  });

  // Fetch tokens
  const {
    data: tokens = [],
    isLoading: tokensLoading,
    isError: tokensError,
    refetch: refetchTokens,
  } = useQuery({
    queryKey: qk.profile.tokens(),
    queryFn: async () => {
      const result = await apiRequest<unknown>('/profile/tokens');
      if (!Array.isArray(result)) {
        throw new Error('Некорректный формат ответа API-токенов');
      }
      return result as ApiToken[];
    },
  });
  const tokenCount = !tokensLoading && !tokensError ? tokens.length : null;

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
      setPasswordErrors({});
    },
    onError: (error: unknown) => {
      const detail = error instanceof Error ? error.message : '';
      if (String(detail).includes('invalid_current_password')) {
        setPasswordErrors({ current: 'Текущий пароль указан неверно' });
        document.getElementById('profile-current-password')?.focus();
        return;
      }
      if (String(detail).includes('password_too_short')) {
        setPasswordErrors({
          new: 'Новый пароль должен быть не короче 8 символов',
        });
        document.getElementById('profile-new-password')?.focus();
        return;
      }
      setPasswordErrors({
        form: 'Не удалось сменить пароль. Попробуйте ещё раз.',
      });
    },
  });

  const saveScopes = useMutation({
    mutationFn: () =>
      apiRequest('/profile/memory-scopes', {
        method: 'PUT',
        body: JSON.stringify({ memory_scope_keys: scopeDraft }),
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

  const handleClosePasswordModal = () => {
    setShowPasswordModal(false);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setRevealPassword(false);
    setPasswordErrors({});
  };

  const handleChangePassword = () => {
    const errors: PasswordErrors = {};
    if (!currentPassword.trim()) errors.current = 'Введите текущий пароль';
    if (newPassword.length < 8)
      errors.new = 'Новый пароль должен быть не короче 8 символов';
    if (!confirmPassword) errors.confirm = 'Повторите новый пароль';
    else if (newPassword !== confirmPassword)
      errors.confirm = 'Новые пароли не совпадают';
    setPasswordErrors(errors);
    const invalidField = errors.current
      ? 'current'
      : errors.new
        ? 'new'
        : errors.confirm
          ? 'confirm'
          : null;
    if (invalidField) {
      document.getElementById(`profile-${invalidField}-password`)?.focus();
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

  const selectTab = (
    tab: 'info' | 'credentials' | 'tenant-management' | 'facts'
  ) => {
    setEditingScopes(false);
    setActiveTab(tab);
  };

  if (profileLoading) {
    return <div className={styles.loading}>Загрузка...</div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Личный кабинет</h1>
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
          Учётные данные
        </button>
        {profile?.is_tenant_admin && (
          <button
            className={
              activeTab === 'tenant-management' ? styles.activeTab : styles.tab
            }
            onClick={() => selectTab('tenant-management')}
            type="button"
          >
            Данные рабочей группы
          </button>
        )}
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
        <div className={styles.infoLayout}>
          <section className={styles.section}>
            {profile && (
              <div className={styles.identityHeader}>
                <div className={styles.identitySummary}>
                  <div className={styles.identityPrimary}>
                    <span className={styles.profileLabel}>Учётная запись</span>
                    <div className={styles.identityHeading}>
                      <h2 className={styles.identityLogin}>{profile.login}</h2>
                      <span className={styles.roleBadge}>
                        {getRoleLabel(profile.role)}
                      </span>
                    </div>
                  </div>
                  <div className={styles.identityMeta}>
                    <div className={styles.profileItem}>
                      <span className={styles.profileLabel}>Email</span>
                      <span className={styles.profileValue}>
                        {profile.email || '—'}
                      </span>
                    </div>
                    <div className={styles.profileItem}>
                      <span className={styles.profileLabel}>Дата регистрации</span>
                      <span className={styles.profileValue}>
                        {formatDate(profile.created_at)}
                      </span>
                    </div>
                  </div>
                </div>
                {profile.auth_provider === 'local' && (
                  <Button
                    variant="outline"
                    onClick={() => setShowPasswordModal(true)}
                  >
                    Сменить пароль
                  </Button>
                )}
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
                onStartEdit={startScopeEdit}
                onCancel={cancelScopeEdit}
                onSave={() => saveScopes.mutate()}
                isSaving={saveScopes.isPending}
              />
            </section>
          )}
        </div>
      )}

      {/* Credentials Section */}
      {activeTab === 'credentials' && (
        <section className={`${styles.section} ${styles.credentialsSection}`}>
          <CredentialsPanel
            mode="user"
            userId={profile?.id}
            tenantId={profile?.tenants?.[0]}
            title="Мои учётные данные"
            description="Зашифрованные данные для подключения к инструментам."
          />
        </section>
      )}

      {/* API Tokens Section */}
      {activeTab === 'credentials' && (
        <section className={`${styles.section} ${styles.tokensSection}`}>
            <div className={styles.sectionHeader}>
              <div className={styles.sectionTitleWithCount}>
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
                  API-токены
                </h2>
                {tokenCount !== null && (
                  <span
                    className={styles.tokenCountBadge}
                    aria-label={`API-токенов: ${tokenCount}`}
                  >
                    {tokenCount}
                  </span>
                )}
              </div>
              <Button
                variant="primary"
                onClick={() => setShowCreateModal(true)}
              >
                Создать токен
              </Button>
            </div>

            <p className={styles.sectionDescription}>
              Персональные токены дают API-доступ от вашего имени. Полный токен
              показывается только при создании; удаление сразу прекращает его
              действие.
            </p>

            {tokensLoading ? (
              <div className={styles.loading}>Загрузка токенов...</div>
            ) : tokensError ? (
              <div className={styles.emptyState} role="alert">
                <h3>Не удалось загрузить API-токены</h3>
                <p>Попробуйте обновить список.</p>
                <Button variant="outline" onClick={() => void refetchTokens()}>
                  Повторить
                </Button>
              </div>
            ) : (
              <>
                {tokens.length === 0 ? (
                  <div className={styles.emptyState}>
                    <h3>Персональных токенов пока нет</h3>
                    <p>
                      Создайте токен, чтобы подключать внешние приложения к API.
                    </p>
                  </div>
                ) : (
                  <div className={styles.tokensList}>
                    {tokens.map(token => {
                      const expiresLabel = formatRelativeDate(token.expires_at);
                      const expirationDate = token.expires_at
                        ? new Date(token.expires_at)
                        : null;
                      const hasValidExpiration =
                        expirationDate &&
                        Number.isFinite(expirationDate.getTime());
                      const isExpired =
                        hasValidExpiration && expirationDate.getTime() <= Date.now();
                      const tokenStatus = !token.is_active
                        ? 'Отключён'
                        : isExpired
                          ? 'Истёк'
                          : token.expires_at && !hasValidExpiration
                            ? 'Срок неизвестен'
                            : expiresLabel
                              ? `Истекает: ${expiresLabel}`
                              : 'Действует';
                      const tokenStatusClass = !token.is_active
                        ? styles.inactive
                        : isExpired
                          ? styles.expired
                          : styles.active;

                      return (
                        <div key={token.id} className={styles.tokenCard}>
                          <div className={styles.tokenInfo}>
                            <div className={styles.tokenHeader}>
                              <span className={styles.tokenName}>{token.name}</span>
                              <span
                                className={`${styles.tokenBadge} ${tokenStatusClass}`}
                              >
                                {tokenStatus}
                              </span>
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
                              {token.expires_at && (
                                <span className={styles.tokenDate}>
                                  Срок: {formatDate(token.expires_at)}
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
              </>
            )}

            {/* Usage Instructions */}
            <details className={styles.usageSection}>
              <summary className={styles.usageSummary}>
                Как использовать токен
              </summary>
              <div className={styles.usageContent}>
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
            </details>
          </section>
      )}

      {activeTab === 'tenant-management' &&
        profile?.is_tenant_admin &&
        profile.tenants?.[0] && (
          <ProfileTenantManagement
            tenantId={profile.tenants[0]}
          />
        )}

      {/* Facts Section */}
      {activeTab === 'facts' && (
        <section className={`${styles.section} ${styles.factsSection}`}>
          <FactsPanel
            mode="profile"
          />
        </section>
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
              <label className={styles.formLabel} htmlFor="profile-token-name">
                Название токена
              </label>
              <Input
                id="profile-token-name"
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
        onClose={handleClosePasswordModal}
        title="Сменить пароль"
      >
        <div className={styles.createForm}>
          <div className={styles.formGroup}>
            <label
              className={styles.formLabel}
              htmlFor="profile-current-password"
            >
              Текущий пароль
            </label>
            <Input
              id="profile-current-password"
              aria-invalid={!!passwordErrors.current}
              aria-describedby={
                passwordErrors.current
                  ? 'profile-current-password-error'
                  : undefined
              }
              type={revealPassword ? 'text' : 'password'}
              value={currentPassword}
              onChange={e => {
                setCurrentPassword(e.target.value);
                setPasswordErrors(previous => ({
                  ...previous,
                  current: undefined,
                  form: undefined,
                }));
              }}
              autoComplete="current-password"
            />
            {passwordErrors.current && (
              <span
                id="profile-current-password-error"
                className={styles.formError}
                role="alert"
              >
                {passwordErrors.current}
              </span>
            )}
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="profile-new-password">
              Новый пароль
            </label>
            <Input
              id="profile-new-password"
              aria-invalid={!!passwordErrors.new}
              aria-describedby={
                passwordErrors.new ? 'profile-new-password-error' : undefined
              }
              type={revealPassword ? 'text' : 'password'}
              value={newPassword}
              onChange={e => {
                setNewPassword(e.target.value);
                setPasswordErrors(previous => ({
                  ...previous,
                  new: undefined,
                  form: undefined,
                }));
              }}
              autoComplete="new-password"
            />
            {passwordErrors.new && (
              <span
                id="profile-new-password-error"
                className={styles.formError}
                role="alert"
              >
                {passwordErrors.new}
              </span>
            )}
          </div>
          <div className={styles.formGroup}>
            <label
              className={styles.formLabel}
              htmlFor="profile-confirm-password"
            >
              Повторите новый пароль
            </label>
            <Input
              id="profile-confirm-password"
              aria-invalid={!!passwordErrors.confirm}
              aria-describedby={
                passwordErrors.confirm
                  ? 'profile-confirm-password-error'
                  : undefined
              }
              type={revealPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={e => {
                setConfirmPassword(e.target.value);
                setPasswordErrors(previous => ({
                  ...previous,
                  confirm: undefined,
                  form: undefined,
                }));
              }}
              autoComplete="new-password"
            />
            {passwordErrors.confirm && (
              <span
                id="profile-confirm-password-error"
                className={styles.formError}
                role="alert"
              >
                {passwordErrors.confirm}
              </span>
            )}
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
          {passwordErrors.form && (
            <p className={styles.formError} role="alert">
              {passwordErrors.form}
            </p>
          )}
          <div className={styles.modalActions}>
            <Button variant="outline" onClick={handleClosePasswordModal}>
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

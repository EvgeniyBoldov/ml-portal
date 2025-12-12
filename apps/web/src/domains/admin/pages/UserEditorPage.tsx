/**
 * UserEditorPage - Edit user with clean UI
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useUser, useUpdateUser, useDeleteUser } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Icon } from '@shared/ui/Icon';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import { Skeleton } from '@shared/ui/Skeleton';
import type { User, Tenant } from '@shared/api/admin';
import styles from './UserEditorPage.module.css';

const ROLES = [
  { value: 'reader', label: 'Читатель', desc: 'Только просмотр' },
  { value: 'editor', label: 'Редактор', desc: 'Просмотр и редактирование' },
  { value: 'admin', label: 'Администратор', desc: 'Полный доступ' },
];

interface FormData {
  email: string;
  role: User['role'];
  tenant_id: string;
  is_active: boolean;
}

export function UserEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);

  const { data: user, isLoading } = useUser(id);
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const { tenants } = useTenants();

  const [formData, setFormData] = useState<FormData>({
    email: '',
    role: 'reader',
    tenant_id: '',
    is_active: true,
  });
  const [newPassword, setNewPassword] = useState('');
  const [activeSection, setActiveSection] = useState<'profile' | 'security'>('profile');

  useEffect(() => {
    if (user) {
      setFormData({
        email: user.email || '',
        role: user.role,
        tenant_id: user.tenant_id || '',
        is_active: user.is_active,
      });
    }
  }, [user]);

  const handleSaveProfile = async () => {
    if (!id) return;
    try {
      await updateUser.mutateAsync({ id, data: formData });
      showSuccess('Профиль обновлён');
    } catch {
      showError('Ошибка сохранения');
    }
  };

  const handleResetPassword = async () => {
    if (!id || !newPassword.trim()) {
      showError('Введите новый пароль');
      return;
    }
    try {
      await updateUser.mutateAsync({
        id,
        data: { password: newPassword, require_password_change: true },
      });
      showSuccess('Пароль сброшен');
      setNewPassword('');
    } catch {
      showError('Ошибка сброса пароля');
    }
  };

  const handleDelete = () => {
    if (!id || !user) return;
    showConfirmDialog({
      title: `Удалить пользователя «${user.login}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Действие необратимо"
          description="Пользователь будет удалён. Все сессии будут завершены."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteUser.mutateAsync(id);
          showSuccess('Пользователь удалён');
          navigate('/admin/users');
        } catch {
          showError('Ошибка удаления');
        }
      },
    });
  };

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.container}>
          <Skeleton height={400} />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className={styles.wrap}>
        <div className={styles.error}>Пользователь не найден</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <button className={styles.backBtn} onClick={() => navigate('/admin/users')}>
            <Icon name="arrow-left" size={20} />
          </button>
          <div className={styles.headerInfo}>
            <div className={styles.avatar}>
              {user.login.charAt(0).toUpperCase()}
            </div>
            <div className={styles.headerTitle}>
              <h1>{user.login}</h1>
              <div className={styles.headerMeta}>
                <Badge variant={user.is_active ? 'success' : 'default'} size="small">
                  {user.is_active ? 'Активен' : 'Неактивен'}
                </Badge>
                <span className={styles.headerDate}>
                  Создан {new Date(user.created_at).toLocaleDateString('ru-RU')}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${activeSection === 'profile' ? styles.active : ''}`}
            onClick={() => setActiveSection('profile')}
          >
            <Icon name="user" size={16} />
            Профиль
          </button>
          <button
            className={`${styles.tab} ${activeSection === 'security' ? styles.active : ''}`}
            onClick={() => setActiveSection('security')}
          >
            <Icon name="lock" size={16} />
            Безопасность
          </button>
        </div>

        {/* Profile Section */}
        {activeSection === 'profile' && (
          <div className={styles.section}>
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <Icon name="info" size={20} />
                <h2>Основная информация</h2>
              </div>
              <div className={styles.cardBody}>
                <div className={styles.field}>
                  <label className={styles.label}>Email</label>
                  <Input
                    type="email"
                    value={formData.email}
                    onChange={e => setFormData(prev => ({ ...prev, email: e.target.value }))}
                    placeholder="user@example.com"
                  />
                </div>

                <div className={styles.field}>
                  <label className={styles.label}>Тенант</label>
                  <select
                    className={styles.select}
                    value={formData.tenant_id}
                    onChange={e => setFormData(prev => ({ ...prev, tenant_id: e.target.value }))}
                  >
                    {(tenants || []).map((t: Tenant) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>

                <div className={styles.switchField}>
                  <div className={styles.switchInfo}>
                    <span className={styles.switchLabel}>Активен</span>
                    <span className={styles.switchDesc}>Пользователь может входить в систему</span>
                  </div>
                  <label className={styles.switch}>
                    <input
                      type="checkbox"
                      checked={formData.is_active}
                      onChange={e => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
                    />
                    <span className={styles.slider} />
                  </label>
                </div>
              </div>
            </div>

            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <Icon name="shield" size={20} />
                <h2>Роль</h2>
              </div>
              <div className={styles.cardBody}>
                <div className={styles.roleGrid}>
                  {ROLES.map(role => (
                    <label
                      key={role.value}
                      className={`${styles.roleCard} ${formData.role === role.value ? styles.selected : ''}`}
                    >
                      <input
                        type="radio"
                        name="role"
                        value={role.value}
                        checked={formData.role === role.value}
                        onChange={e => setFormData(prev => ({ ...prev, role: e.target.value as User['role'] }))}
                      />
                      <div className={styles.roleContent}>
                        <span className={styles.roleName}>{role.label}</span>
                        <span className={styles.roleDesc}>{role.desc}</span>
                      </div>
                      {formData.role === role.value && (
                        <Icon name="check" size={16} className={styles.roleCheck} />
                      )}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className={styles.actions}>
              <Button variant="secondary" onClick={() => navigate('/admin/users')}>
                Отмена
              </Button>
              <Button onClick={handleSaveProfile} disabled={updateUser.isPending}>
                {updateUser.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>
            </div>
          </div>
        )}

        {/* Security Section */}
        {activeSection === 'security' && (
          <div className={styles.section}>
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <Icon name="key" size={20} />
                <h2>Сброс пароля</h2>
              </div>
              <div className={styles.cardBody}>
                <p className={styles.hint}>
                  Установите новый пароль для пользователя. При следующем входе ему будет предложено сменить пароль.
                </p>
                <div className={styles.field}>
                  <label className={styles.label}>Новый пароль</label>
                  <Input
                    type="password"
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    placeholder="Введите новый пароль"
                  />
                </div>
                <Button onClick={handleResetPassword} disabled={updateUser.isPending || !newPassword.trim()}>
                  Сбросить пароль
                </Button>
              </div>
            </div>

            <div className={styles.card + ' ' + styles.dangerCard}>
              <div className={styles.cardHeader}>
                <Icon name="alert-triangle" size={20} />
                <h2>Опасная зона</h2>
              </div>
              <div className={styles.cardBody}>
                <div className={styles.dangerAction}>
                  <div className={styles.dangerInfo}>
                    <span className={styles.dangerTitle}>Удалить пользователя</span>
                    <span className={styles.dangerDesc}>
                      Это действие нельзя отменить. Все данные пользователя будут удалены.
                    </span>
                  </div>
                  <Button variant="danger" onClick={handleDelete}>
                    Удалить
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default UserEditorPage;

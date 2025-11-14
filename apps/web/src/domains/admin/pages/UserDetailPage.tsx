/**
 * UserDetailPage - User detail and management
 */
import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  useUser,
  useUpdateUser,
  useDeleteUser,
} from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { Skeleton } from '@shared/ui/Skeleton';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import type { User, UserUpdate, Tenant } from '@shared/api/admin';
import type { UseMutationResult } from '@tanstack/react-query';
import styles from './UserDetailPage.module.css';

type AppState = ReturnType<typeof useAppStore.getState>;
type UpdateUserMutation = UseMutationResult<
  User,
  Error,
  { id: string; data: UserUpdate },
  unknown
>;

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const activeTab = useAppStore(
    (state: AppState) => state.activeTabs[`user-${id}`] || 'profile'
  );
  const setActiveTab = useAppStore((state: AppState) => state.setActiveTab);
  const showConfirmDialog = useAppStore(
    (state: AppState) => state.showConfirmDialog
  );

  const { data: user, isLoading } = useUser(id);
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const { tenants } = useTenants();

  const handleTabChange = (tab: string) => {
    setActiveTab(`user-${id}`, tab);
  };

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <Skeleton width={600} height={400} />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className={styles.wrap}>
        <div className={styles.errorState}>User not found</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>User: {user.login}</h1>
        </div>

        <div className={styles.tabs}>
          <button
            className={activeTab === 'profile' ? styles.active : ''}
            onClick={() => handleTabChange('profile')}
          >
            Profile
          </button>
          <button
            className={activeTab === 'security' ? styles.active : ''}
            onClick={() => handleTabChange('security')}
          >
            Security
          </button>
          <button
            className={activeTab === 'audit' ? styles.active : ''}
            onClick={() => handleTabChange('audit')}
          >
            Audit
          </button>
        </div>

        <div className={styles.content}>
          {activeTab === 'profile' && (
            <ProfileTab
              user={user}
              updateUser={updateUser}
              tenants={tenants || []}
            />
          )}
          {activeTab === 'security' && (
            <SecurityTab
              user={user}
              updateUser={updateUser}
              showSuccess={showSuccess}
            />
          )}
          {activeTab === 'audit' && <AuditTab userId={id!} />}
        </div>

        <div className={styles.actions}>
          <Button
            variant="danger"
            onClick={() => {
              if (!id) return;
              showConfirmDialog({
                title: `Удалить пользователя «${user.login}»?`,
                confirmLabel: 'Удалить',
                cancelLabel: 'Отмена',
                variant: 'danger',
                message: (
                  <Alert
                    variant="danger"
                    title="Пользователь будет удалён"
                    description={
                      <>
                        Удаление нельзя отменить. Все связанные сессии будут
                        завершены.
                      </>
                    }
                  />
                ),
                onConfirm: async () => {
                  try {
                    await deleteUser.mutateAsync(id);
                    showSuccess(`Пользователь ${user.login} удалён`);
                    navigate('/admin/users');
                  } catch (error) {
                    console.error('Failed to delete user:', error);
                    showError(
                      'Не удалось удалить пользователя. Попробуйте снова.'
                    );
                  }
                },
              });
            }}
          >
            Delete User
          </Button>
        </div>
      </div>
    </div>
  );
}

interface ProfileTabProps {
  user: User;
  updateUser: UpdateUserMutation;
  tenants: Tenant[];
}

function ProfileTab({ user, updateUser, tenants }: ProfileTabProps) {
  interface ProfileFormState {
    email: string;
    role: User['role'];
    is_active: boolean;
    tenant_id: string;
  }

  const [formData, setFormData] = useState<ProfileFormState>({
    email: user.email || '',
    role: user.role,
    is_active: user.is_active,
    tenant_id: user.tenant_id,
  });

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await updateUser.mutateAsync({ id: user.id, data: formData });
    } catch {
      // Error handled by toast
    }
  };

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.formGroup}>
        <label>Email</label>
        <Input
          value={formData.email}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
            setFormData(prev => ({ ...prev, email: event.target.value }))
          }
        />
      </div>
      <div className={styles.formGroup}>
        <label>Role</label>
        <Select
          value={formData.role}
          onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
            setFormData(prev => ({
              ...prev,
              role: event.target.value as User['role'],
            }))
          }
        >
          <option value="reader">Reader</option>
          <option value="editor">Editor</option>
          <option value="admin">Admin</option>
        </Select>
      </div>
      <div className={styles.formGroup}>
        <label>Tenant</label>
        <Select
          value={formData.tenant_id}
          onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
            setFormData(prev => ({ ...prev, tenant_id: event.target.value }))
          }
        >
          {tenants.map(t => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </div>
      <div className={styles.formGroup}>
        <label>
          <input
            type="checkbox"
            checked={formData.is_active}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
              setFormData(prev => ({
                ...prev,
                is_active: event.target.checked,
              }))
            }
          />
          Active
        </label>
      </div>
      <div className={styles.formActions}>
        <Button type="submit" disabled={updateUser.isPending}>
          {updateUser.isPending ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

interface SecurityTabProps {
  user: User;
  updateUser: UpdateUserMutation;
  showSuccess: (message: string) => void;
}

function SecurityTab({ user, updateUser, showSuccess }: SecurityTabProps) {
  const [password, setPassword] = useState('');

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!password) return;

    try {
      await updateUser.mutateAsync({
        id: user.id,
        data: { password, require_password_change: true },
      });
      showSuccess('Password reset successfully');
      setPassword('');
    } catch {
      // Error handled by toast
    }
  };

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.formGroup}>
        <label>New Password</label>
        <Input
          type="password"
          value={password}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
            setPassword(event.target.value)
          }
        />
      </div>
      <div className={styles.formActions}>
        <Button type="submit" disabled={updateUser.isPending}>
          {updateUser.isPending ? 'Resetting...' : 'Reset Password'}
        </Button>
      </div>
    </form>
  );
}

function AuditTab({ userId }: { userId: string }) {
  const { isLoading } = useUser(userId);
  // TODO: Implement audit log query

  if (isLoading) {
    return <Skeleton width={500} height={200} />;
  }

  return <div>Audit log for user</div>;
}

export default UserDetailPage;

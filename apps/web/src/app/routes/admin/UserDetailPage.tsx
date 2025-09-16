import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  adminApi,
  type User,
  type UserToken,
  type AuditLog,
  TOKEN_SCOPES,
} from '../../../shared/api/admin';
import { RoleBadge, StatusBadge } from '../../../shared/ui/RoleBadge';
import Button from '../../../shared/ui/Button';
import Input from '../../../shared/ui/Input';
import Select from '../../../shared/ui/Select';
import Modal from '../../../shared/ui/Modal';
// import { Skeleton } from '../../../shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '../../../shared/ui/Toast';
import styles from './UserDetailPage.module.css';

type TabType = 'profile' | 'security' | 'tokens' | 'audit';

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // State
  const [user, setUser] = useState<User | null>(null);
  const [tokens, setTokens] = useState<UserToken[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('profile');
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    role: 'reader' as 'admin' | 'editor' | 'reader',
    email: '',
    is_active: true,
  });

  // Token creation modal
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [tokenForm, setTokenForm] = useState({
    name: '',
    scopes: [] as string[],
    expires_at: '',
  });

  // Load user data
  useEffect(() => {
    if (!id) return;

    const loadUserData = async () => {
      try {
        setLoading(true);
        const [userData, tokensData, auditData] = await Promise.all([
          adminApi.getUser(id),
          adminApi.getUserTokens(id),
          adminApi.getAuditLogs({ actor_user_id: id, limit: 10 }),
        ]);

        setUser(userData);
        setTokens(tokensData.tokens);
        setAuditLogs(auditData.logs);
        setFormData({
          role: userData.role,
          email: userData.email || '',
          is_active: userData.is_active,
        });
      } catch (error) {
        console.error('Failed to load user data:', error);
        showError('Failed to load user data. Please try again.');
      } finally {
        setLoading(false);
      }
    };

    loadUserData();
  }, [id, showError]);

  // Handle form submission
  const handleSave = async () => {
    if (!user) return;

    try {
      setSaving(true);
      const updatedUser = await adminApi.updateUser(user.id, formData);
      setUser(updatedUser);
      setEditing(false);
      showSuccess('User updated successfully');
    } catch (error) {
      console.error('Failed to update user:', error);
      showError('Failed to update user. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Handle password reset
  const handlePasswordReset = async () => {
    if (!user) return;

    if (!window.confirm(`Reset password for user ${user.login}?`)) {
      return;
    }

    try {
      const response = await adminApi.resetUserPassword(user.id, {});
      if (response.password) {
        showSuccess(
          `Password reset successfully. New password: ${response.password}`
        );
      } else {
        showSuccess('Password reset email sent successfully');
      }
    } catch (error) {
      console.error('Failed to reset password:', error);
      showError('Failed to reset password. Please try again.');
    }
  };

  // Handle token creation
  const handleCreateToken = async () => {
    if (!user) return;

    try {
      const response = await adminApi.createUserToken(user.id, {
        name: tokenForm.name,
        scopes: tokenForm.scopes,
        expires_at: tokenForm.expires_at || undefined,
      });

      setTokens(prev => [...prev, response]);
      setShowTokenModal(false);
      setTokenForm({ name: '', scopes: [], expires_at: '' });

      if (response.token_plain_once) {
        showSuccess(`Token created successfully: ${response.token_plain_once}`);
      } else {
        showSuccess('Token created successfully');
      }
    } catch (error) {
      console.error('Failed to create token:', error);
      showError('Failed to create token. Please try again.');
    }
  };

  // Handle token revocation
  const handleRevokeToken = async (tokenId: string) => {
    if (!window.confirm('Are you sure you want to revoke this token?')) {
      return;
    }

    try {
      await adminApi.revokeToken(tokenId);
      setTokens(prev => prev.filter(token => token.id !== tokenId));
      showSuccess('Token revoked successfully');
    } catch (error) {
      console.error('Failed to revoke token:', error);
      showError('Failed to revoke token. Please try again.');
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <div className={styles.loadingSpinner} />
          <p>Loading user data...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>
          <div className={styles.emptyStateIcon}>👤</div>
          <div className={styles.emptyStateTitle}>User not found</div>
          <div className={styles.emptyStateDescription}>
            The requested user could not be found.
          </div>
          <Button onClick={() => navigate('/admin/users')}>
            Back to Users
          </Button>
        </div>
      </div>
    );
  }

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map(word => word[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>User Details</h1>
        <div className={styles.pageActions}>
          <Button variant="outline" onClick={() => navigate('/admin/users')}>
            Back to Users
          </Button>
          {editing ? (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  setEditing(false);
                  setFormData({
                    role: user.role,
                    email: user.email || '',
                    is_active: user.is_active,
                  });
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </>
          ) : (
            <Button onClick={() => setEditing(true)}>Edit User</Button>
          )}
        </div>
      </div>

      <div className={styles.userInfo}>
        <div className={styles.userAvatar}>{getInitials(user.login)}</div>
        <div className={styles.userDetails}>
          <h2 className={styles.userName}>{user.login}</h2>
          <div className={styles.userRole}>
            <RoleBadge role={user.role} size="large" />
          </div>
          <div className={styles.userMeta}>
            <div className={styles.userMetaItem}>
              <strong>Status:</strong> <StatusBadge active={user.is_active} />
            </div>
            <div className={styles.userMetaItem}>
              <strong>Email:</strong> {user.email || 'Not provided'}
            </div>
            <div className={styles.userMetaItem}>
              <strong>Created:</strong>{' '}
              {new Date(user.created_at).toLocaleDateString()}
            </div>
            <div className={styles.userMetaItem}>
              <strong>Last Updated:</strong>{' '}
              {new Date(user.updated_at).toLocaleDateString()}
            </div>
          </div>
        </div>
      </div>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'profile' ? styles.active : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          Profile
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'security' ? styles.active : ''}`}
          onClick={() => setActiveTab('security')}
        >
          Security
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'tokens' ? styles.active : ''}`}
          onClick={() => setActiveTab('tokens')}
        >
          Tokens ({tokens.length})
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'audit' ? styles.active : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          Audit
        </button>
      </div>

      {/* Profile Tab */}
      <div
        className={`${styles.tabContent} ${activeTab === 'profile' ? styles.active : ''}`}
      >
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Profile Information</h3>
          <div className={styles.sectionContent}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Login</label>
              <Input value={user.login} disabled className={styles.formInput} />
              <div className={styles.formHelp}>
                Username cannot be changed after creation.
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Email</label>
              {editing ? (
                <Input
                  type="email"
                  value={formData.email}
                  onChange={e =>
                    setFormData(prev => ({ ...prev, email: e.target.value }))
                  }
                  className={styles.formInput}
                />
              ) : (
                <Input
                  value={user.email || 'Not provided'}
                  disabled
                  className={styles.formInput}
                />
              )}
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Role</label>
              {editing ? (
                <Select
                  value={formData.role}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      role: e.target.value as any,
                    }))
                  }
                  className={styles.formSelect}
                >
                  <option value="reader">Reader</option>
                  <option value="editor">Editor</option>
                  <option value="admin">Admin</option>
                </Select>
              ) : (
                <div>
                  <RoleBadge role={user.role} />
                </div>
              )}
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Status</label>
              {editing ? (
                <Select
                  value={formData.is_active ? 'active' : 'inactive'}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      is_active: e.target.value === 'active',
                    }))
                  }
                  className={styles.formSelect}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </Select>
              ) : (
                <div>
                  <StatusBadge active={user.is_active} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Security Tab */}
      <div
        className={`${styles.tabContent} ${activeTab === 'security' ? styles.active : ''}`}
      >
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Security Settings</h3>
          <div className={styles.sectionContent}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Password Reset</label>
              <div className={styles.formHelp}>
                Reset the user&apos;s password. They will be required to change
                it on next login.
              </div>
              <Button variant="outline" onClick={handlePasswordReset}>
                Reset Password
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Tokens Tab */}
      <div
        className={`${styles.tabContent} ${activeTab === 'tokens' ? styles.active : ''}`}
      >
        <div className={styles.section}>
          <div className={styles.sectionTitle}>
            Personal Access Tokens
            <Button
              size="small"
              onClick={() => setShowTokenModal(true)}
              style={{ marginLeft: 'var(--spacing-md)' }}
            >
              Create Token
            </Button>
          </div>

          {tokens.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateIcon}>🔑</div>
              <div className={styles.emptyStateTitle}>No tokens</div>
              <div className={styles.emptyStateDescription}>
                This user has no personal access tokens.
              </div>
            </div>
          ) : (
            <div className={styles.tokensList}>
              {tokens.map(token => (
                <div key={token.id} className={styles.tokenItem}>
                  <div className={styles.tokenInfo}>
                    <div className={styles.tokenName}>{token.name}</div>
                    <div className={styles.tokenScopes}>
                      {token.scopes.map(scope => (
                        <span key={scope.scope} className={styles.tokenScope}>
                          {scope.scope}
                        </span>
                      ))}
                    </div>
                    <div className={styles.tokenMeta}>
                      Created: {new Date(token.created_at).toLocaleDateString()}
                      {token.expires_at && (
                        <>
                          {' '}
                          • Expires:{' '}
                          {new Date(token.expires_at).toLocaleDateString()}
                        </>
                      )}
                      {token.last_used_at && (
                        <>
                          {' '}
                          • Last used:{' '}
                          {new Date(token.last_used_at).toLocaleDateString()}
                        </>
                      )}
                      {token.revoked_at && (
                        <>
                          {' '}
                          • Revoked:{' '}
                          {new Date(token.revoked_at).toLocaleDateString()}
                        </>
                      )}
                    </div>
                  </div>
                  <div className={styles.tokenActions}>
                    {!token.revoked_at && (
                      <Button
                        size="small"
                        variant="danger"
                        onClick={() => handleRevokeToken(token.id)}
                      >
                        Revoke
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Audit Tab */}
      <div
        className={`${styles.tabContent} ${activeTab === 'audit' ? styles.active : ''}`}
      >
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Recent Activity</h3>

          {auditLogs.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateIcon}>📋</div>
              <div className={styles.emptyStateTitle}>No activity</div>
              <div className={styles.emptyStateDescription}>
                No recent activity found for this user.
              </div>
            </div>
          ) : (
            <div className={styles.auditList}>
              {auditLogs.map(log => (
                <div key={log.id} className={styles.auditItem}>
                  <div className={styles.auditInfo}>
                    <div className={styles.auditAction}>{log.action}</div>
                    <div className={styles.auditDetails}>
                      {log.object_type && log.object_id && (
                        <>
                          Object: {log.object_type} ({log.object_id})
                        </>
                      )}
                    </div>
                    <div className={styles.auditMeta}>
                      {log.ip && <>IP: {log.ip}</>}
                      {log.user_agent && <> • {log.user_agent}</>}
                    </div>
                  </div>
                  <div className={styles.auditTime}>
                    {new Date(log.ts).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Token Creation Modal */}
      <Modal
        open={showTokenModal}
        onClose={() => setShowTokenModal(false)}
        title="Create Personal Access Token"
      >
        <div className={styles.sectionContent}>
          <div className={styles.formGroup}>
            <label className={`${styles.formLabel} ${styles.required}`}>
              Token Name
            </label>
            <Input
              value={tokenForm.name}
              onChange={e =>
                setTokenForm(prev => ({ ...prev, name: e.target.value }))
              }
              placeholder="Enter token name"
              className={styles.formInput}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={`${styles.formLabel} ${styles.required}`}>
              Scopes
            </label>
            <div className={styles.formHelp}>
              Select the permissions this token should have.
            </div>
            <div
              style={{
                maxHeight: '200px',
                overflowY: 'auto',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--border-radius)',
                padding: 'var(--spacing-sm)',
              }}
            >
              {TOKEN_SCOPES.map(scope => (
                <label key={scope.scope} className={styles.formCheckbox}>
                  <input
                    type="checkbox"
                    checked={tokenForm.scopes.includes(scope.scope)}
                    onChange={e => {
                      if (e.target.checked) {
                        setTokenForm(prev => ({
                          ...prev,
                          scopes: [...prev.scopes, scope.scope],
                        }));
                      } else {
                        setTokenForm(prev => ({
                          ...prev,
                          scopes: prev.scopes.filter(s => s !== scope.scope),
                        }));
                      }
                    }}
                    className={styles.formCheckboxInput}
                  />
                  <span className={styles.formCheckboxLabel}>
                    <strong>{scope.scope}</strong> - {scope.description}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Expires At</label>
            <Input
              type="datetime-local"
              value={tokenForm.expires_at}
              onChange={e =>
                setTokenForm(prev => ({ ...prev, expires_at: e.target.value }))
              }
              className={styles.formInput}
            />
            <div className={styles.formHelp}>
              Leave empty for no expiration.
            </div>
          </div>
        </div>

        <div className={styles.formActions}>
          <Button variant="outline" onClick={() => setShowTokenModal(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCreateToken}
            disabled={!tokenForm.name || tokenForm.scopes.length === 0}
          >
            Create Token
          </Button>
        </div>
      </Modal>
    </div>
  );
}

export default UserDetailPage;

import React, { useState, useEffect } from 'react';
import { adminApi, type SystemStatus } from '../../../shared/api/admin';
import Button from '../../../shared/ui/Button';
import { Skeleton } from '../../../shared/ui/Skeleton';
import { useErrorToast } from '../../../shared/ui/Toast';
import styles from './EmailSettingsPage.module.css';

export function EmailSettingsPage() {
  const showError = useErrorToast();

  // State
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Load system status
  useEffect(() => {
    const loadSystemStatus = async () => {
      try {
        setLoading(true);
        const systemStatus = await adminApi.getSystemStatus();
        setStatus(systemStatus);
      } catch (error) {
        console.error('Failed to load system status:', error);
        showError('Failed to load system status. Please try again.');
      } finally {
        setLoading(false);
      }
    };

    loadSystemStatus();
  }, [showError]);

  // Refresh status
  const handleRefresh = async () => {
    try {
      setLoading(true);
      const systemStatus = await adminApi.getSystemStatus();
      setStatus(systemStatus);
    } catch (error) {
      console.error('Failed to refresh system status:', error);
      showError('Failed to refresh system status. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <div className={styles.loadingSpinner} />
          <p>Loading email settings...</p>
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <div className="text-danger">Failed to load system status</div>
        </div>
      </div>
    );
  }

  const getStatusBadge = () => {
    if (!status.email_enabled) {
      return { className: styles.disabled, text: 'Disabled' };
    }

    switch (status.email_status) {
      case 'ok':
        return { className: styles.enabled, text: 'Enabled' };
      case 'error':
        return { className: styles.error, text: 'Error' };
      case 'disabled':
        return { className: styles.disabled, text: 'Disabled' };
      default:
        return { className: styles.disabled, text: 'Unknown' };
    }
  };

  const statusBadge = getStatusBadge();

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Email Settings</h1>
        <p className={styles.pageDescription}>
          Monitor email system status and configuration.
        </p>
      </div>

      {/* Email Status */}
      <div className={styles.statusCard}>
        <div className={styles.statusHeader}>
          <h2 className={styles.statusTitle}>Email System Status</h2>
          <span className={`${styles.statusBadge} ${statusBadge.className}`}>
            {statusBadge.text}
          </span>
        </div>

        <div className={styles.statusInfo}>
          <div className={styles.statusItem}>
            <div className={styles.statusLabel}>Email Enabled</div>
            <div
              className={`${styles.statusValue} ${styles.boolean} ${status.email_enabled ? styles.true : styles.false}`}
            >
              {status.email_enabled ? 'Yes' : 'No'}
            </div>
          </div>

          <div className={styles.statusItem}>
            <div className={styles.statusLabel}>Email Status</div>
            <div className={styles.statusValue}>{status.email_status}</div>
          </div>

          <div className={styles.statusItem}>
            <div className={styles.statusLabel}>Total Users</div>
            <div className={styles.statusValue}>
              {status.total_users.toLocaleString()}
            </div>
          </div>

          <div className={styles.statusItem}>
            <div className={styles.statusLabel}>Active Users</div>
            <div className={styles.statusValue}>
              {status.active_users.toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* Email Configuration Info */}
      <div className={styles.infoCard}>
        <h3 className={styles.infoTitle}>Email Configuration</h3>
        <div className={styles.infoContent}>
          <p>
            Email functionality is controlled by environment variables and
            system configuration. The following settings determine how email
            features work in the system:
          </p>

          <ul className={styles.infoList}>
            <li className={styles.infoListItem}>
              <span className={styles.infoListIcon}>📧</span>
              <span className={styles.infoListText}>
                <strong>EMAIL_ENABLED</strong> - Master switch for email
                functionality
              </span>
            </li>
            <li className={styles.infoListItem}>
              <span className={styles.infoListIcon}>🔧</span>
              <span className={styles.infoListText}>
                <strong>SMTP Settings</strong> - SMTP server configuration for
                sending emails
              </span>
            </li>
            <li className={styles.infoListItem}>
              <span className={styles.infoListIcon}>🔐</span>
              <span className={styles.infoListText}>
                <strong>Authentication</strong> - SMTP username and password for
                server access
              </span>
            </li>
            <li className={styles.infoListItem}>
              <span className={styles.infoListIcon}>🛡️</span>
              <span className={styles.infoListText}>
                <strong>TLS/SSL</strong> - Secure connection settings for email
                transmission
              </span>
            </li>
          </ul>
        </div>
      </div>

      {/* Warning for disabled email */}
      {!status.email_enabled && (
        <div className={styles.warningCard}>
          <h3 className={styles.warningTitle}>⚠️ Email System Disabled</h3>
          <div className={styles.warningContent}>
            <p>Email functionality is currently disabled. This means:</p>
            <ul className={styles.infoList}>
              <li className={styles.infoListItem}>
                <span className={styles.infoListIcon}>❌</span>
                <span className={styles.infoListText}>
                  Password reset emails will not be sent
                </span>
              </li>
              <li className={styles.infoListItem}>
                <span className={styles.infoListIcon}>❌</span>
                <span className={styles.infoListText}>
                  User creation emails will not be sent
                </span>
              </li>
              <li className={styles.infoListItem}>
                <span className={styles.infoListIcon}>✅</span>
                <span className={styles.infoListText}>
                  Offline password reset will be used instead
                </span>
              </li>
            </ul>
            <p>
              To enable email functionality, configure the EMAIL_ENABLED
              environment variable and provide valid SMTP settings.
            </p>
          </div>
        </div>
      )}

      {/* System Metrics */}
      <div className={styles.metricsCard}>
        <h3 className={styles.metricsTitle}>System Metrics</h3>
        <div className={styles.metricsGrid}>
          <div className={styles.metricItem}>
            <div className={styles.metricValue}>
              {loading ? (
                <Skeleton width={60} height={32} />
              ) : (
                status.total_users
              )}
            </div>
            <div className={styles.metricLabel}>Total Users</div>
          </div>

          <div className={styles.metricItem}>
            <div className={styles.metricValue}>
              {loading ? (
                <Skeleton width={60} height={32} />
              ) : (
                status.active_users
              )}
            </div>
            <div className={styles.metricLabel}>Active Users</div>
          </div>

          <div className={styles.metricItem}>
            <div className={styles.metricValue}>
              {loading ? (
                <Skeleton width={60} height={32} />
              ) : (
                status.total_tokens
              )}
            </div>
            <div className={styles.metricLabel}>Total Tokens</div>
          </div>

          <div className={styles.metricItem}>
            <div className={styles.metricValue}>
              {loading ? (
                <Skeleton width={60} height={32} />
              ) : (
                status.active_tokens
              )}
            </div>
            <div className={styles.metricLabel}>Active Tokens</div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 'var(--spacing-md)',
        }}
      >
        <Button onClick={handleRefresh} variant="outline">
          Refresh Status
        </Button>
      </div>
    </div>
  );
}

export default EmailSettingsPage;

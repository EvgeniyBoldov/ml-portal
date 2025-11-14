/**
 * EmailSettingsPage - Email settings management
 */
import React, { useState } from 'react';
import {
  useEmailSettings,
  useUpdateEmailSettings,
} from '@shared/api/hooks/useAdmin';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { Skeleton } from '@shared/ui/Skeleton';
import styles from './EmailSettingsPage.module.css';

export function EmailSettingsPage() {
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const { data, isLoading } = useEmailSettings();
  const updateMutation = useUpdateEmailSettings();

  const [settings, setSettings] = useState({
    smtp_host: '',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    from_email: '',
    from_name: '',
  });

  React.useEffect(() => {
    if (data) {
      setSettings({
        smtp_host: data.smtp_host || '',
        smtp_port: data.smtp_port || 587,
        smtp_user: data.smtp_user || '',
        smtp_password: '',
        from_email: data.from_email || '',
        from_name: data.from_name || '',
      });
    }
  }, [data]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await updateMutation.mutateAsync(settings);
      showSuccess('Email settings updated successfully');
    } catch {
      showError('Failed to update email settings');
    }
  };

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <h1>Email Settings</h1>
          <Skeleton width={400} height={300} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <h1 className={styles.title}>Email Settings</h1>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.formGroup}>
            <label>SMTP Host</label>
            <Input
              value={settings.smtp_host}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setSettings(prev => ({
                  ...prev,
                  smtp_host: event.target.value,
                }))
              }
              placeholder="smtp.example.com"
            />
          </div>

          <div className={styles.formGroup}>
            <label>SMTP Port</label>
            <Input
              type="number"
              value={settings.smtp_port}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setSettings(prev => ({
                  ...prev,
                  smtp_port: Number.parseInt(event.target.value, 10) || 587,
                }))
              }
            />
          </div>

          <div className={styles.formGroup}>
            <label>SMTP User</label>
            <Input
              value={settings.smtp_user}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setSettings(prev => ({
                  ...prev,
                  smtp_user: event.target.value,
                }))
              }
            />
          </div>

          <div className={styles.formGroup}>
            <label>SMTP Password</label>
            <Input
              type="password"
              value={settings.smtp_password}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setSettings(prev => ({
                  ...prev,
                  smtp_password: event.target.value,
                }))
              }
              placeholder="Leave blank to keep current"
            />
          </div>

          <div className={styles.formGroup}>
            <label>From Email</label>
            <Input
              value={settings.from_email}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setSettings(prev => ({
                  ...prev,
                  from_email: event.target.value,
                }))
              }
              placeholder="noreply@example.com"
            />
          </div>

          <div className={styles.formGroup}>
            <label>From Name</label>
            <Input
              value={settings.from_name}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setSettings(prev => ({
                  ...prev,
                  from_name: event.target.value,
                }))
              }
              placeholder="ML Portal"
            />
          </div>

          <div className={styles.formActions}>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Saving...' : 'Save Settings'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default EmailSettingsPage;

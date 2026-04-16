/**
 * SandboxLayout — layout for sandbox pages.
 * Uses AppHeader with sandbox branding and simple content area.
 */
import React from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { AppHeader } from '@/shared/ui/AppHeader';
import { useAuth } from '@/shared/hooks/useAuth';
import styles from './SandboxLayout.module.css';

export default function SandboxLayout() {
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  return (
    <div className={styles.shell}>
      <AppHeader
        brandName="Песочница"
        variant="default"
        userLabel={user?.email || user?.role || ''}
        showSandboxButton={false}
        showBackToApp
        onBackToAppClick={() => navigate('/gpt/chat')}
        onLogout={logout}
      />

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}

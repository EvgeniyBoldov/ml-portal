import React from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { AdminSidebar } from '../components/AdminSidebar';
import { useAuth } from '@/shared/hooks/useAuth';
import { AppHeader } from '@/shared/ui/AppHeader';
import styles from './AdminLayout.module.css';

export function AdminLayout() {
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  return (
    <div className={styles.shell}>
      <AppHeader
        brandName="Почемучка"
        variant="default"
        userLabel={user?.email || user?.role || ''}
        showBackToApp
        onBackToAppClick={() => navigate('/gpt/chat')}
        onLogout={logout}
      />

      <div className={styles.layout}>
        <AdminSidebar />
        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AdminLayout;

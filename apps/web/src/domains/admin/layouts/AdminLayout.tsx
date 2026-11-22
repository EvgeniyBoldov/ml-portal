import { Outlet, useMatch, useNavigate } from 'react-router-dom';
import { AdminSidebar } from '../components/AdminSidebar';
import { useAuth } from '@/shared/hooks/useAuth';
import { AppHeader } from '@/shared/ui/AppHeader';
import styles from './AdminLayout.module.css';

function AdminLayout() {
  const navigate = useNavigate();
  const isAccessPage = useMatch('/admin/access/*');
  const isPeriodicTasksPage = useMatch('/admin/periodic-tasks/*');
  const isToolsPage = useMatch('/admin/tools/*');
  const isConnectorsPage = useMatch('/admin/connectors/*');
  const { logout, user } = useAuth();

  return (
    <div className={styles.shell}>
      <AppHeader
        brandName="Почемучка"
        brandTo="/admin"
        variant="default"
        userLabel={user?.email || user?.role || ''}
        showBackToApp
        onBackToAppClick={() => navigate('/gpt/chat')}
        onLogout={logout}
      />

      <div className={(isAccessPage || isPeriodicTasksPage || isToolsPage || isConnectorsPage) ? `${styles.layout} ${styles.compactLayout}` : styles.layout}>
        <AdminSidebar />
        <main className={styles.main}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AdminLayout;

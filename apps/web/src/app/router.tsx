import React, { Suspense, lazy } from 'react';
import { Navigate, createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AdminGuard } from './router/AdminGuard';
import { Skeleton } from '@shared/ui/Skeleton';

// Auth pages
const GPTGate = lazy(() => import('@/domains/auth/pages/GPTGate'));
const Login = lazy(() => import('@/domains/auth/pages/Login'));

// GPT pages
const GPTLayout = lazy(() => import('@/domains/gpt/pages/GPTLayout'));
const ChatPage = lazy(() => import('@/domains/gpt/pages/ChatPage'));
const ProfilePage = lazy(() => import('@/domains/profile/pages/ProfilePage'));

// Common pages
const NotFound = lazy(() => import('@/domains/common/pages/NotFound'));

// Admin pages
const AdminLayout = lazy(() => import('@/domains/admin/layouts/AdminLayout'));
const DashboardPage = lazy(() => import('@/domains/admin/pages/DashboardPage'));
const UsersListPage = lazy(() => import('@/domains/admin/pages/UsersListPage'));
const UserPage = lazy(() => import('@/domains/admin/pages/UserPage'));
const TenantsListPage = lazy(() => import('@/domains/admin/pages/TenantsListPage'));
const TenantPage = lazy(() => import('@/domains/admin/pages/TenantPage'));
const ModelPage = lazy(() => import('@/domains/admin/pages/ModelPage').then(m => ({ default: m.default })));
const AuditPage = lazy(() => import('@/domains/admin/pages/AuditPage'));
const DiscoveredToolsPage = lazy(() => import('@/domains/admin/pages/DiscoveredToolsPage').then(m => ({ default: m.DiscoveredToolsPage })));
const DiscoveredToolViewPage = lazy(() => import('@/domains/admin/pages/DiscoveredToolViewPage').then(m => ({ default: m.DiscoveredToolViewPage })));
const AgentListPage = lazy(() => import('@/domains/admin/pages/AgentListPage').then(m => ({ default: m.AgentListPage })));
const AgentPage = lazy(() => import('@/domains/admin/pages/AgentPage').then(m => ({ default: m.AgentPage })));
const AgentVersionPage = lazy(() => import('@/domains/admin/pages/AgentVersionPage').then(m => ({ default: m.AgentVersionPage })));
const AgentRunsPage = lazy(() => import('@/domains/admin/pages/AgentRunsPage').then(m => ({ default: m.AgentRunsPage })));
const AgentRunPage = lazy(() => import('@/domains/admin/pages/AgentRunPage').then(m => ({ default: m.AgentRunPage })));
const CollectionListPage = lazy(() => import('@/domains/admin/pages/CollectionListPage'));
const CollectionPage = lazy(() => import('@/domains/admin/pages/CollectionPage'));
const CollectionVersionPage = lazy(() => import('@/domains/admin/pages/CollectionVersionPage').then(m => ({ default: m.CollectionVersionPage })));
const InstancesListPage = lazy(() => import('@/domains/admin/pages/InstancesListPage'));
const InstancePage = lazy(() => import('@/domains/admin/pages/InstancePage').then(m => ({ default: m.InstancePage })));
const RbacListPage = lazy(() => import('@/domains/admin/pages/RbacListPage').then(m => ({ default: m.RbacListPage })));
const RbacRulePage = lazy(() => import('@/domains/admin/pages/RbacRulePage').then(m => ({ default: m.RbacRulePage })));
const PlatformSettingsPage = lazy(() => import('@/domains/admin/pages/PlatformSettingsPage').then(m => ({ default: m.PlatformSettingsPage })));
const OrchestrationPage = lazy(() => import('@/domains/admin/pages/OrchestrationPage').then(m => ({ default: m.OrchestrationPage })));
const CredentialPage = lazy(() => import('@/domains/admin/pages/CredentialPage').then(m => ({ default: m.default })));

// Sandbox pages
const SandboxLayout = lazy(() => import('@/domains/sandbox/layouts/SandboxLayout'));
const SandboxHomePage = lazy(() => import('@/domains/sandbox/pages/SandboxHomePage'));
const SandboxSessionPage = lazy(() => import('@/domains/sandbox/pages/SandboxSessionPage'));
const SandboxListPage = lazy(() => import('@/domains/sandbox/pages/SandboxListPage'));

// Collections pages (user-facing)
const CollectionsListPage = lazy(() => import('@/domains/collections/pages/CollectionsListPage'));
const CollectionDataPage = lazy(() => import('@/domains/collections/pages/CollectionDataPage'));


const withSuspense = (el: React.ReactNode) => (
  <Suspense fallback={<div style={{ padding: '2rem' }}><Skeleton variant="card" /></div>}>
    {el}
  </Suspense>
);

const router = createBrowserRouter([
  { path: '/', element: withSuspense(<Login />) },
  { path: '/login', element: withSuspense(<Login />) },
  {
    path: '/gpt',
    element: withSuspense(<GPTGate>{withSuspense(<GPTLayout />)}</GPTGate>),
    children: [
      { path: 'chat', element: withSuspense(<ChatPage />) },
      { path: 'chat/:chatId', element: withSuspense(<ChatPage />) },
      { path: 'collections', element: withSuspense(<CollectionsListPage />) },
      { path: 'collections/:slug', element: withSuspense(<CollectionDataPage />) },
      { path: 'profile', element: withSuspense(<ProfilePage />) },
    ],
  },
  {
    path: '/sandbox',
    element: withSuspense(<GPTGate>{withSuspense(<SandboxLayout />)}</GPTGate>),
    children: [
      { index: true, element: withSuspense(<SandboxHomePage />) },
      { path: ':sessionId', element: withSuspense(<SandboxSessionPage />) },
    ],
  },
  {
    path: '/admin',
    element: withSuspense(
      <GPTGate>
        <AdminGuard>{withSuspense(<AdminLayout />)}</AdminGuard>
      </GPTGate>
    ),
    children: [
      { index: true, element: withSuspense(<DashboardPage />) },
      { path: 'users', element: withSuspense(<UsersListPage />) },
      { path: 'users/new', element: withSuspense(<UserPage />) },
      { path: 'users/:id', element: withSuspense(<UserPage />) },
      { path: 'tenants', element: withSuspense(<TenantsListPage />) },
      { path: 'tenants/new', element: withSuspense(<TenantPage />) },
      { path: 'tenants/:id', element: withSuspense(<TenantPage />) },
      { path: 'platform/models/new', element: withSuspense(<ModelPage />) },
      { path: 'platform/models/:id', element: withSuspense(<ModelPage />) },
      { path: 'audit', element: withSuspense(<AuditPage />) },
      { path: 'tools', element: withSuspense(<DiscoveredToolsPage />) },
      { path: 'tools/discovered/:id', element: withSuspense(<DiscoveredToolViewPage />) },
      { path: 'agents', element: withSuspense(<AgentListPage />) },
      { path: 'agents/new', element: withSuspense(<AgentPage />) },
      { path: 'agents/:id', element: withSuspense(<AgentPage />) },
      { path: 'agents/:id/versions/new', element: withSuspense(<AgentVersionPage />) },
      { path: 'agents/:id/versions/:version', element: withSuspense(<AgentVersionPage />) },
      { path: 'agent-runs', element: withSuspense(<AgentRunsPage />) },
      { path: 'agent-runs/:id', element: withSuspense(<AgentRunPage />) },
      { path: 'collections', element: withSuspense(<CollectionListPage />) },
      { path: 'collections/new', element: withSuspense(<CollectionPage />) },
      { path: 'collections/:slug', element: withSuspense(<CollectionPage />) },
      { path: 'collections/:id/versions/new', element: withSuspense(<CollectionVersionPage />) },
      { path: 'collections/:id/versions/:version', element: withSuspense(<CollectionVersionPage />) },
      { path: 'connectors', element: withSuspense(<InstancesListPage />) },
      { path: 'connectors/new', element: withSuspense(<InstancePage />) },
      { path: 'connectors/:id', element: withSuspense(<InstancePage />) },
      { path: 'connectors/:id/edit', element: withSuspense(<InstancePage />) },
      { path: 'instances', element: <Navigate to="/admin/connectors" replace /> },
      { path: 'instances/new', element: withSuspense(<InstancePage />) },
      { path: 'instances/:id', element: withSuspense(<InstancePage />) },
      { path: 'instances/:id/edit', element: withSuspense(<InstancePage />) },
      { path: 'rbac', element: withSuspense(<RbacListPage />) },
      { path: 'rbac/:id', element: withSuspense(<RbacRulePage />) },
      { path: 'platform', element: withSuspense(<PlatformSettingsPage />) },
      { path: 'credentials/new', element: withSuspense(<CredentialPage />) },
      { path: 'credentials/:id', element: withSuspense(<CredentialPage />) },
      { path: 'orchestration', element: withSuspense(<OrchestrationPage />) },
      { path: 'sandbox', element: withSuspense(<SandboxListPage />) },
    ],
  },
  { path: '*', element: withSuspense(<NotFound />) },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

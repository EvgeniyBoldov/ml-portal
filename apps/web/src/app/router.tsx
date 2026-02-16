import React, { Suspense, lazy } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AdminGuard } from './router/AdminGuard';
import { Skeleton } from '@shared/ui/Skeleton';

// Auth pages
const GPTGate = lazy(() => import('@/domains/auth/pages/GPTGate'));
const Login = lazy(() => import('@/domains/auth/pages/Login'));

// GPT pages
const GPTLayout = lazy(() => import('@/domains/gpt/pages/GPTLayout'));
const ChatPage = lazy(() => import('@/domains/gpt/pages/ChatPage'));
const RagPage = lazy(() => import('@/domains/rag/pages/RagPage'));
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
const ModelsPage = lazy(() => import('@/domains/admin/pages/ModelsPage'));
const ModelEditorPage = lazy(() => import('@/domains/admin/pages/ModelEditorPage').then(m => ({ default: m.ModelEditorPage })));
const AuditPage = lazy(() => import('@/domains/admin/pages/AuditPage'));
const EmailSettingsPage = lazy(() => import('@/domains/admin/pages/EmailSettingsPage'));
const ToolsListPage = lazy(() => import('@/domains/admin/pages/ToolsListPage').then(m => ({ default: m.ToolsListPage })));
const ToolGroupViewPage = lazy(() => import('@/domains/admin/pages/ToolGroupViewPage').then(m => ({ default: m.ToolGroupViewPage })));
const ToolPage = lazy(() => import('@/domains/admin/pages/ToolPage').then(m => ({ default: m.ToolPage })));
const ToolVersionPage = lazy(() => import('@/domains/admin/pages/ToolVersionPage').then(m => ({ default: m.ToolVersionPage })));
const ViewBackendReleasePage = lazy(() => import('@/domains/admin/pages/ViewBackendReleasePage').then(m => ({ default: m.ViewBackendReleasePage })));
const AgentListPage = lazy(() => import('@/domains/admin/pages/AgentListPage').then(m => ({ default: m.AgentListPage })));
const AgentEditorPage = lazy(() => import('@/domains/admin/pages/AgentEditorPage').then(m => ({ default: m.AgentEditorPage })));
const AgentRouterPage = lazy(() => import('@/domains/admin/pages/AgentRouterPage').then(m => ({ default: m.AgentRouterPage })));
const AgentVersionPage = lazy(() => import('@/domains/admin/pages/AgentVersionPage').then(m => ({ default: m.AgentVersionPage })));
const AgentRunsPage = lazy(() => import('@/domains/admin/pages/AgentRunsPage').then(m => ({ default: m.AgentRunsPage })));
const AgentRunPage = lazy(() => import('@/domains/admin/pages/AgentRunPage').then(m => ({ default: m.AgentRunPage })));
const CollectionsPage = lazy(() => import('@/domains/admin/pages/CollectionsPage'));
const CreateCollectionPage = lazy(() => import('@/domains/admin/pages/CreateCollectionPage'));
const ViewCollectionPage = lazy(() => import('@/domains/admin/pages/ViewCollectionPage'));
const InstancesListPage = lazy(() => import('@/domains/admin/pages/InstancesListPage').then(m => ({ default: m.InstancesListPage })));
const InstancePage = lazy(() => import('@/domains/admin/pages/InstancePage').then(m => ({ default: m.InstancePage })));
const LimitsListPage = lazy(() => import('@/domains/admin/pages/LimitsListPage').then(m => ({ default: m.LimitsListPage })));
const LimitPage = lazy(() => import('@/domains/admin/pages/LimitPage').then(m => ({ default: m.LimitPage })));
const LimitVersionPage = lazy(() => import('@/domains/admin/pages/LimitVersionPage').then(m => ({ default: m.LimitVersionPage })));
const PoliciesListPage = lazy(() => import('@/domains/admin/pages/PoliciesListPage').then(m => ({ default: m.PoliciesListPage })));
const PolicyPage = lazy(() => import('@/domains/admin/pages/PolicyPage').then(m => ({ default: m.PolicyPage })));
const PolicyVersionPage = lazy(() => import('@/domains/admin/pages/PolicyVersionPage').then(m => ({ default: m.PolicyVersionPage })));
const RbacListPage = lazy(() => import('@/domains/admin/pages/RbacListPage').then(m => ({ default: m.RbacListPage })));
const RbacRulePage = lazy(() => import('@/domains/admin/pages/RbacRulePage').then(m => ({ default: m.RbacRulePage })));
const RbacRuleCreatePage = lazy(() => import('@/domains/admin/pages/RbacRuleCreatePage').then(m => ({ default: m.RbacRuleCreatePage })));
const PlatformSettingsPage = lazy(() => import('@/domains/admin/pages/PlatformSettingsPage').then(m => ({ default: m.PlatformSettingsPage })));
const CredentialPage = lazy(() => import('@/domains/admin/pages/CredentialPage').then(m => ({ default: m.default })));
const CredentialsListPage = lazy(() => import('@/domains/admin/pages/CredentialsListPage').then(m => ({ default: m.default })));

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
      { path: 'rag', element: withSuspense(<RagPage />) },
      { path: 'collections', element: withSuspense(<CollectionsListPage />) },
      { path: 'collections/:slug', element: withSuspense(<CollectionDataPage />) },
      { path: 'profile', element: withSuspense(<ProfilePage />) },
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
      { path: 'users/:id/rbac/new', element: withSuspense(<RbacRuleCreatePage />) },
      { path: 'tenants', element: withSuspense(<TenantsListPage />) },
      { path: 'tenants/new', element: withSuspense(<TenantPage />) },
      { path: 'tenants/:id', element: withSuspense(<TenantPage />) },
      { path: 'tenants/:id/rbac/new', element: withSuspense(<RbacRuleCreatePage />) },
      { path: 'models', element: withSuspense(<ModelsPage />) },
      { path: 'models/new', element: withSuspense(<ModelEditorPage />) },
      { path: 'models/:id', element: withSuspense(<ModelEditorPage />) },
      { path: 'audit', element: withSuspense(<AuditPage />) },
      { path: 'tools', element: withSuspense(<ToolsListPage />) },
      { path: 'tools/groups/:groupSlug', element: withSuspense(<ToolGroupViewPage />) },
      { path: 'tools/:toolSlug', element: withSuspense(<ToolPage />) },
      { path: 'tools/:toolSlug/backend/:version', element: withSuspense(<ViewBackendReleasePage />) },
      { path: 'tools/:toolSlug/versions/new', element: withSuspense(<ToolVersionPage />) },
      { path: 'tools/:toolSlug/versions/:version', element: withSuspense(<ToolVersionPage />) },
      { path: 'agents', element: withSuspense(<AgentListPage />) },
      { path: 'agents/new', element: withSuspense(<AgentEditorPage />) },
      { path: 'agents/router', element: withSuspense(<AgentRouterPage />) },
      { path: 'agents/:slug', element: withSuspense(<AgentEditorPage />) },
      { path: 'agents/:slug/versions/new', element: withSuspense(<AgentVersionPage />) },
      { path: 'agents/:slug/versions/:version', element: withSuspense(<AgentVersionPage />) },
      { path: 'agent-runs', element: withSuspense(<AgentRunsPage />) },
      { path: 'agent-runs/:id', element: withSuspense(<AgentRunPage />) },
      { path: 'collections', element: withSuspense(<CollectionsPage />) },
      { path: 'collections/new', element: withSuspense(<CreateCollectionPage />) },
      { path: 'collections/:id', element: withSuspense(<ViewCollectionPage />) },
      { path: 'limits', element: withSuspense(<LimitsListPage />) },
      { path: 'limits/new', element: withSuspense(<LimitPage />) },
      { path: 'limits/:slug', element: withSuspense(<LimitPage />) },
      { path: 'limits/:slug/versions/new', element: withSuspense(<LimitVersionPage />) },
      { path: 'limits/:slug/versions/:version', element: withSuspense(<LimitVersionPage />) },
      { path: 'policies', element: withSuspense(<PoliciesListPage />) },
      { path: 'policies/new', element: withSuspense(<PolicyPage />) },
      { path: 'policies/:slug', element: withSuspense(<PolicyPage />) },
      { path: 'policies/:slug/versions/new', element: withSuspense(<PolicyVersionPage />) },
      { path: 'policies/:slug/versions/:version', element: withSuspense(<PolicyVersionPage />) },
      { path: 'instances', element: withSuspense(<InstancesListPage />) },
      { path: 'instances/new', element: withSuspense(<InstancePage />) },
      { path: 'instances/:id', element: withSuspense(<InstancePage />) },
      { path: 'instances/:id/edit', element: withSuspense(<InstancePage />) },
      { path: 'rbac', element: withSuspense(<RbacListPage />) },
      { path: 'rbac/:id', element: withSuspense(<RbacRulePage />) },
      { path: 'platform', element: withSuspense(<PlatformSettingsPage />) },
      { path: 'platform/rbac/new', element: withSuspense(<RbacRuleCreatePage />) },
      { path: 'credentials', element: withSuspense(<CredentialsListPage />) },
      { path: 'credentials/new', element: withSuspense(<CredentialPage />) },
      { path: 'credentials/:id', element: withSuspense(<CredentialPage />) },
      { path: 'settings/email', element: withSuspense(<EmailSettingsPage />) },
    ],
  },
  { path: '*', element: withSuspense(<NotFound />) },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

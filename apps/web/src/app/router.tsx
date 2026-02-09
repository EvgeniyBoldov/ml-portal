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
const UsersPage = lazy(() => import('@/domains/admin/pages/UsersPage'));
const UserEditorPage = lazy(() => import('@/domains/admin/pages/UserEditorPage'));
const TenantsPage = lazy(() => import('@/domains/admin/pages/TenantsPage'));
const TenantEditorPage = lazy(() => import('@/domains/admin/pages/TenantEditorPage'));
const ModelsPage = lazy(() => import('@/domains/admin/pages/ModelsPage'));
const ModelEditorPage = lazy(() => import('@/domains/admin/pages/ModelEditorPage').then(m => ({ default: m.ModelEditorPage })));
const AuditPage = lazy(() => import('@/domains/admin/pages/AuditPage'));
const EmailSettingsPage = lazy(() => import('@/domains/admin/pages/EmailSettingsPage'));
const PromptsListPage = lazy(() => import('@/domains/admin/pages/PromptsListPage'));
const PromptEditorPage = lazy(() => import('@/domains/admin/pages/PromptEditorPage').then(m => ({ default: m.PromptEditorPage })));
const PromptVersionPage = lazy(() => import('@/domains/admin/pages/PromptVersionPage').then(m => ({ default: m.PromptVersionPage })));
const ToolsPage = lazy(() => import('@/domains/admin/pages/ToolsPage').then(m => ({ default: m.ToolsPage })));
const ToolGroupViewPage = lazy(() => import('@/domains/admin/pages/ToolGroupViewPage').then(m => ({ default: m.ToolGroupViewPage })));
const ToolViewPage = lazy(() => import('@/domains/admin/pages/ToolViewPage').then(m => ({ default: m.ToolViewPage })));
const ToolReleasePage = lazy(() => import('@/domains/admin/pages/ToolReleasePage').then(m => ({ default: m.ToolReleasePage })));
const AgentRegistryPage = lazy(() => import('@/domains/admin/pages/AgentRegistryPage').then(m => ({ default: m.AgentRegistryPage })));
const AgentEditorPage = lazy(() => import('@/domains/admin/pages/AgentEditorPage').then(m => ({ default: m.AgentEditorPage })));
const AgentVersionPage = lazy(() => import('@/domains/admin/pages/AgentVersionPage').then(m => ({ default: m.AgentVersionPage })));
const AgentRunsPage = lazy(() => import('@/domains/admin/pages/AgentRunsPage').then(m => ({ default: m.AgentRunsPage })));
const CollectionsPage = lazy(() => import('@/domains/admin/pages/CollectionsPage'));
const CreateCollectionPage = lazy(() => import('@/domains/admin/pages/CreateCollectionPage'));
const ViewCollectionPage = lazy(() => import('@/domains/admin/pages/ViewCollectionPage'));
const InstancesPage = lazy(() => import('@/domains/admin/pages/InstancesPage').then(m => ({ default: m.InstancesPage })));
const InstanceEditorPage = lazy(() => import('@/domains/admin/pages/InstanceEditorPage').then(m => ({ default: m.InstanceEditorPage })));
const InstanceViewPage = lazy(() => import('@/domains/admin/pages/InstanceViewPage').then(m => ({ default: m.InstanceViewPage })));
const LimitsListPage = lazy(() => import('@/domains/admin/pages/LimitsListPage').then(m => ({ default: m.LimitsListPage })));
const LimitEditorPage = lazy(() => import('@/domains/admin/pages/LimitEditorPage').then(m => ({ default: m.LimitEditorPage })));
const LimitVersionPage = lazy(() => import('@/domains/admin/pages/LimitVersionPage').then(m => ({ default: m.LimitVersionPage })));
const RoutingLogsPage = lazy(() => import('@/domains/admin/pages/RoutingLogsPage').then(m => ({ default: m.RoutingLogsPage })));
const PoliciesListPage = lazy(() => import('@/domains/admin/pages/PoliciesListPage').then(m => ({ default: m.PoliciesListPage })));
const PolicyEditorPage = lazy(() => import('@/domains/admin/pages/PolicyEditorPage').then(m => ({ default: m.PolicyEditorPage })));
const PolicyVersionPage = lazy(() => import('@/domains/admin/pages/PolicyVersionPage').then(m => ({ default: m.PolicyVersionPage })));
const RbacListPage = lazy(() => import('@/domains/admin/pages/RbacListPage').then(m => ({ default: m.RbacListPage })));
const RbacPolicyPage = lazy(() => import('@/domains/admin/pages/RbacPolicyPage').then(m => ({ default: m.RbacPolicyPage })));
const PlatformSettingsPage = lazy(() => import('@/domains/admin/pages/PlatformSettingsPage').then(m => ({ default: m.PlatformSettingsPage })));

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
      { path: 'users', element: withSuspense(<UsersPage />) },
      { path: 'users/new', element: withSuspense(<UserEditorPage />) },
      { path: 'users/:id', element: withSuspense(<UserEditorPage />) },
      { path: 'tenants', element: withSuspense(<TenantsPage />) },
      { path: 'tenants/new', element: withSuspense(<TenantEditorPage />) },
      { path: 'tenants/:id', element: withSuspense(<TenantEditorPage />) },
      { path: 'models', element: withSuspense(<ModelsPage />) },
      { path: 'models/new', element: withSuspense(<ModelEditorPage />) },
      { path: 'models/:id', element: withSuspense(<ModelEditorPage />) },
      { path: 'audit', element: withSuspense(<AuditPage />) },
      { path: 'prompts', element: withSuspense(<PromptsListPage />) },
      { path: 'prompts/:slug', element: withSuspense(<PromptEditorPage />) },
      { path: 'prompts/:slug/versions/new', element: withSuspense(<PromptVersionPage />) },
      { path: 'prompts/:slug/versions/:version', element: withSuspense(<PromptVersionPage />) },
      { path: 'tools', element: withSuspense(<ToolsPage />) },
      { path: 'tools/groups/:groupSlug', element: withSuspense(<ToolGroupViewPage />) },
      { path: 'tools/:toolSlug', element: withSuspense(<ToolViewPage />) },
      { path: 'tools/:toolSlug/versions/new', element: withSuspense(<ToolReleasePage />) },
      { path: 'tools/:toolSlug/versions/:version', element: withSuspense(<ToolReleasePage />) },
      { path: 'agents', element: withSuspense(<AgentRegistryPage />) },
      { path: 'agents/new', element: withSuspense(<AgentEditorPage />) },
      { path: 'agents/:slug', element: withSuspense(<AgentEditorPage />) },
      { path: 'agents/:slug/versions/new', element: withSuspense(<AgentVersionPage />) },
      { path: 'agents/:slug/versions/:version', element: withSuspense(<AgentVersionPage />) },
      { path: 'agent-runs', element: withSuspense(<AgentRunsPage />) },
      { path: 'collections', element: withSuspense(<CollectionsPage />) },
      { path: 'collections/new', element: withSuspense(<CreateCollectionPage />) },
      { path: 'collections/:id', element: withSuspense(<ViewCollectionPage />) },
      { path: 'limits', element: withSuspense(<LimitsListPage />) },
      { path: 'limits/new', element: withSuspense(<LimitEditorPage />) },
      { path: 'limits/:slug', element: withSuspense(<LimitEditorPage />) },
      { path: 'limits/:slug/versions/new', element: withSuspense(<LimitVersionPage />) },
      { path: 'limits/:slug/versions/:version', element: withSuspense(<LimitVersionPage />) },
      { path: 'policies', element: withSuspense(<PoliciesListPage />) },
      { path: 'policies/new', element: withSuspense(<PolicyEditorPage />) },
      { path: 'policies/:slug', element: withSuspense(<PolicyEditorPage />) },
      { path: 'policies/:slug/versions/new', element: withSuspense(<PolicyVersionPage />) },
      { path: 'policies/:slug/versions/:version', element: withSuspense(<PolicyVersionPage />) },
      { path: 'instances', element: withSuspense(<InstancesPage />) },
      { path: 'instances/new', element: withSuspense(<InstanceEditorPage />) },
      { path: 'instances/:id', element: withSuspense(<InstanceViewPage />) },
      { path: 'instances/:id/edit', element: withSuspense(<InstanceEditorPage />) },
      { path: 'rbac', element: withSuspense(<RbacListPage />) },
      { path: 'rbac/new', element: withSuspense(<RbacPolicyPage />) },
      { path: 'rbac/:slug', element: withSuspense(<RbacPolicyPage />) },
      { path: 'platform', element: withSuspense(<PlatformSettingsPage />) },
            { path: 'routing-logs', element: withSuspense(<RoutingLogsPage />) },
      { path: 'settings/email', element: withSuspense(<EmailSettingsPage />) },
    ],
  },
  { path: '*', element: withSuspense(<NotFound />) },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

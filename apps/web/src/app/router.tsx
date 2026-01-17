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
const UsersPage = lazy(() => import('@/domains/admin/pages/UsersPageNew'));
const CreateUserPage = lazy(() => import('@/domains/admin/pages/CreateUserPage'));
const UserEditorPage = lazy(() => import('@/domains/admin/pages/UserEditorPage'));
const TenantsPage = lazy(() => import('@/domains/admin/pages/TenantsPageNew'));
const TenantEditorPage = lazy(() => import('@/domains/admin/pages/TenantEditorPage'));
const ModelsPage = lazy(() => import('@/domains/admin/pages/ModelsPage'));
const ModelEditorPage = lazy(() => import('@/domains/admin/pages/ModelEditorPage').then(m => ({ default: m.ModelEditorPage })));
const AuditPage = lazy(() => import('@/domains/admin/pages/AuditPage'));
const EmailSettingsPage = lazy(() => import('@/domains/admin/pages/EmailSettingsPage'));
const PromptRegistryPage = lazy(() => import('@/domains/admin/pages/PromptRegistryPage').then(m => ({ default: m.PromptRegistryPage })));
const PromptEditorPage = lazy(() => import('@/domains/admin/pages/PromptEditorPage').then(m => ({ default: m.PromptEditorPage })));
const ToolsPage = lazy(() => import('@/domains/admin/pages/ToolsPage').then(m => ({ default: m.ToolsPage })));
const ToolEditorPage = lazy(() => import('@/domains/admin/pages/ToolEditorPage').then(m => ({ default: m.ToolEditorPage })));
const AgentRegistryPage = lazy(() => import('@/domains/admin/pages/AgentRegistryPage').then(m => ({ default: m.AgentRegistryPage })));
const AgentEditorPage = lazy(() => import('@/domains/admin/pages/AgentEditorPage').then(m => ({ default: m.AgentEditorPage })));
const AgentRunsPage = lazy(() => import('@/domains/admin/pages/AgentRunsPage').then(m => ({ default: m.AgentRunsPage })));


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
      { path: 'users/new', element: withSuspense(<CreateUserPage />) },
      { path: 'users/:id', element: withSuspense(<UserEditorPage />) },
      { path: 'tenants', element: withSuspense(<TenantsPage />) },
      { path: 'tenants/new', element: withSuspense(<TenantEditorPage />) },
      { path: 'tenants/:id/edit', element: withSuspense(<TenantEditorPage />) },
      { path: 'models', element: withSuspense(<ModelsPage />) },
      { path: 'models/new', element: withSuspense(<ModelEditorPage />) },
      { path: 'models/:id', element: withSuspense(<ModelEditorPage />) },
      { path: 'audit', element: withSuspense(<AuditPage />) },
      { path: 'prompts', element: withSuspense(<PromptRegistryPage />) },
      { path: 'prompts/new', element: withSuspense(<PromptEditorPage />) },
      { path: 'prompts/:slug', element: withSuspense(<PromptEditorPage />) },
      { path: 'tools', element: withSuspense(<ToolsPage />) },
      { path: 'tools/new', element: withSuspense(<ToolEditorPage />) },
      { path: 'tools/:slug', element: withSuspense(<ToolEditorPage />) },
      { path: 'agents', element: withSuspense(<AgentRegistryPage />) },
      { path: 'agents/new', element: withSuspense(<AgentEditorPage />) },
      { path: 'agents/:slug', element: withSuspense(<AgentEditorPage />) },
      { path: 'agent-runs', element: withSuspense(<AgentRunsPage />) },
      { path: 'settings/email', element: withSuspense(<EmailSettingsPage />) },
    ],
  },
  { path: '*', element: withSuspense(<NotFound />) },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

import React, { Suspense, lazy } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

const GPTGate = lazy(() => import('@pages/GPTGate'));
const Login = lazy(() => import('@pages/Login'));
const GPTLayout = lazy(() => import('@pages/gpt/GPTLayout'));
const ChatPage = lazy(() => import('@pages/gpt/ChatPage'));
const AnalyzePage = lazy(() => import('@pages/gpt/AnalyzePage'));
const RagPage = lazy(() => import('@pages/gpt/Rag'));
const NotFound = lazy(() => import('@pages/NotFound'));

// Admin routes
const AdminLayout = lazy(() => import('@pages/admin/AdminLayout'));
const UsersPage = lazy(() => import('@pages/admin/UsersPage'));
const CreateUserPage = lazy(() => import('@pages/admin/CreateUserPage'));
const UserDetailPage = lazy(() => import('@pages/admin/UserDetailPage'));
const AuditPage = lazy(() => import('@pages/admin/AuditPage'));
const EmailSettingsPage = lazy(
  () => import('@pages/admin/EmailSettingsPage')
);

const withSuspense = (el: React.ReactNode) => (
  <Suspense fallback={<div />}>{el}</Suspense>
);

const router = createBrowserRouter([
  { path: '/login', element: withSuspense(<Login />) },
  {
    path: '/gpt',
    element: withSuspense(<GPTGate>{withSuspense(<GPTLayout />)}</GPTGate>),
    children: [
      { path: 'chat', element: withSuspense(<ChatPage />) },
      { path: 'chat/:chatId', element: withSuspense(<ChatPage />) },
      { path: 'analyze', element: withSuspense(<AnalyzePage />) },
      { path: 'rag', element: withSuspense(<RagPage />) },
    ],
  },
  {
    path: '/admin',
    element: withSuspense(<GPTGate>{withSuspense(<AdminLayout />)}</GPTGate>),
    children: [
      { index: true, element: withSuspense(<UsersPage />) },
      { path: 'users', element: withSuspense(<UsersPage />) },
      { path: 'users/new', element: withSuspense(<CreateUserPage />) },
      { path: 'users/:id', element: withSuspense(<UserDetailPage />) },
      { path: 'audit', element: withSuspense(<AuditPage />) },
      { path: 'settings/email', element: withSuspense(<EmailSettingsPage />) },
    ],
  },
  { path: '*', element: withSuspense(<NotFound />) },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

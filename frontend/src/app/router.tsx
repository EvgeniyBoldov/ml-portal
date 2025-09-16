import React, { Suspense, lazy } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

const GPTGate = lazy(() => import('./routes/GPTGate'));
const Login = lazy(() => import('./routes/Login'));
const GPTLayout = lazy(() => import('./routes/gpt/GPTLayout'));
const ChatPage = lazy(() => import('./routes/gpt/ChatPage'));
const AnalyzePage = lazy(() => import('./routes/gpt/AnalyzePage'));
const RagPage = lazy(() => import('./routes/gpt/Rag'));
const NotFound = lazy(() => import('./routes/NotFound'));

// Admin routes
const AdminLayout = lazy(() => import('./routes/admin/AdminLayout'));
const UsersPage = lazy(() => import('./routes/admin/UsersPage'));
const CreateUserPage = lazy(() => import('./routes/admin/CreateUserPage'));
const UserDetailPage = lazy(() => import('./routes/admin/UserDetailPage'));
const AuditPage = lazy(() => import('./routes/admin/AuditPage'));
const EmailSettingsPage = lazy(
  () => import('./routes/admin/EmailSettingsPage')
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

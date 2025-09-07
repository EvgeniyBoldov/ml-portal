import React, { Suspense, lazy } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

const GPTGate = lazy(() => import('./routes/GPTGate'))
const Login = lazy(() => import('./routes/Login'))
const GPTLayout = lazy(() => import('./routes/gpt/GPTLayout'))
const ChatPage = lazy(() => import('./routes/gpt/ChatPage'))
const AnalyzePage = lazy(() => import('./routes/gpt/AnalyzePage'))
const RagPage = lazy(() => import('./routes/gpt/RagPage'))
const NotFound = lazy(() => import('./routes/NotFound'))

const withSuspense = (el: React.ReactNode) => <Suspense fallback={<div />}>{el}</Suspense>

const router = createBrowserRouter([
  { path: '/login', element: withSuspense(<Login />) },
  {
    path: '/gpt',
    element: withSuspense(<GPTGate>{withSuspense(<GPTLayout />)}</GPTGate>),
    children: [
      { path: 'chat', element: withSuspense(<ChatPage />) },
      { path: 'chat/:chatId', element: withSuspense(<ChatPage />) },
      { path: 'analyze', element: withSuspense(<AnalyzePage />) },
      { path: 'rag', element: withSuspense(<RagPage />) }
    ]
  },
  { path: '*', element: withSuspense(<NotFound />) }
])

export default function AppRouter() {
  return <RouterProvider router={router} />
}

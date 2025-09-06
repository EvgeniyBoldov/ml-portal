import React from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import GPTGate from './routes/GPTGate'
import Login from './routes/Login'
import GPTLayout from './routes/gpt/GPTLayout'
import ChatPage from './routes/gpt/ChatPage'
import AnalyzePage from './routes/gpt/AnalyzePage'
import RagPage from './routes/gpt/RagPage'

const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/gpt',
    element: <GPTGate><GPTLayout /></GPTGate>,
    children: [
      { path: 'chat', element: <ChatPage /> },
      { path: 'chat/:chatId', element: <ChatPage /> },
      { path: 'analyze', element: <AnalyzePage /> },
      { path: 'rag', element: <RagPage /> }
    ]
  },
  { path: '*', element: <Login /> }
])

export default function AppRouter() {
  return <RouterProvider router={router} />
}

import React from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import Button from '@shared/ui/Button'
import styles from './GPTLayout.module.css'
import { useAuth } from '@app/store/auth'
import ThemeSwitch from '@shared/ui/ThemeSwitch'

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

export default function GPTLayout() {
  const nav = useNavigate()
  const { logout, user } = useAuth()
  const isAdmin = (user?.role || '').toLowerCase() === 'admin'

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.logo}>LLM+RAG</div>

        <nav className={styles.nav}>
          <div className={styles.seg}>
            <NavLink to="/gpt/chat" className={({isActive}) => [styles.segBtn, isActive ? styles.active : ''].join(' ')}>Chat</NavLink>
            <NavLink to="/gpt/analyze" className={({isActive}) => [styles.segBtn, isActive ? styles.active : ''].join(' ')}>Analyze</NavLink>
            {isAdmin && (
              <NavLink to="/gpt/rag" className={({isActive}) => [styles.segBtn, isActive ? styles.active : ''].join(' ')}>RAG</NavLink>
            )}
          </div>

          <div className={styles.headerRightCluster}>
            <ThemeSwitch />
            {USE_MOCKS && <span className={styles.mocks}>Mocks ON</span>}
          </div>
        </nav>

        <div className={styles.right}>
          <span className={styles.user}>{user?.fio || user?.login}</span>
          <Button variant="ghost" onClick={async () => { await logout(); nav('/login') }}>Logout</Button>
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}

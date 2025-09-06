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
        {/* Left: logo + brand */}
        <div className={styles.brand}>
          {/* Положи файл в frontend/public/logo.svg */}
          <img src="/logo.png" alt="Почемучка logo" onError={(e)=>{ (e.target as HTMLImageElement).style.display='none' }} />
          <div className={styles.brandName}>Почемучка</div>
        </div>

        {/* Center: segmented nav (50% header width) */}
        <nav className={styles.nav}>
          <div className={styles.segWrap}>
            <div className={styles.seg}>
              <NavLink to="/gpt/chat" className={({isActive}) => [styles.segBtn, isActive ? styles.active : ''].join(' ')}>Chat</NavLink>
              <NavLink to="/gpt/analyze" className={({isActive}) => [styles.segBtn, isActive ? styles.active : ''].join(' ')}>Analyze</NavLink>
              {isAdmin && (
                <NavLink to="/gpt/rag" className={({isActive}) => [styles.segBtn, isActive ? styles.active : ''].join(' ')}>RAG</NavLink>
              )}
            </div>
          </div>
        </nav>

        {/* Right: mocks -> role -> theme -> logout */}
        <div className={styles.right}>
          {USE_MOCKS && <span className={styles.mocks}>Mocks ON</span>}
          <span className={styles.user}>{user?.role || ''}</span>
          <ThemeSwitch />
          <Button variant="ghost" onClick={async () => { await logout(); nav('/login') }}>Logout</Button>
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>

      <footer className={styles.footer}>{/* пустой подвал, заполним позже */}</footer>
    </div>
  )
}

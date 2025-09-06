import React, { useEffect, useState } from 'react'

type Mode = 'light' | 'dark'
const KEY = 'theme'

function getInitial(): Mode {
  const saved = (localStorage.getItem(KEY) as Mode | null)
  if (saved === 'light' || saved === 'dark') return saved
  // prefer system
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  return prefersDark ? 'dark' : 'light'
}

export default function ThemeSwitch() {
  const [mode, setMode] = useState<Mode>(getInitial())

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode === 'dark' ? '' : 'light')
    localStorage.setItem(KEY, mode)
  }, [mode])

  return (
    <button
      onClick={() => setMode(m => m === 'light' ? 'dark' : 'light')}
      title={mode === 'light' ? 'Switch to dark' : 'Switch to light'}
      style={{
        border: '1px solid rgba(255,255,255,.14)',
        background: 'transparent',
        color: 'inherit',
        borderRadius: 12,
        padding: '6px 10px',
        cursor: 'pointer'
      }}
    >
      {mode === 'light' ? '☀️ Light' : '🌙 Dark'}
    </button>
  )
}

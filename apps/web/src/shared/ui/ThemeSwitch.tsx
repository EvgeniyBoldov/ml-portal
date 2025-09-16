import React, { useEffect, useState } from 'react';

type Mode = 'light' | 'dark';
const KEY = 'theme';

function getInitial(): Mode {
  const saved = localStorage.getItem(KEY) as Mode | null;
  if (saved === 'light' || saved === 'dark') return saved;
  const prefersDark =
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}

export default function ThemeSwitch() {
  const [mode, setMode] = useState<Mode>(getInitial());

  useEffect(() => {
    const root = document.documentElement;
    if (mode === 'dark') {
      root.removeAttribute('data-theme'); // было '' — убираем атрибут полностью
    } else {
      root.setAttribute('data-theme', 'light');
    }
    localStorage.setItem(KEY, mode);
  }, [mode]);

  return (
    <button
      onClick={() => setMode(m => (m === 'dark' ? 'light' : 'dark'))}
      aria-label="Переключить тему"
      style={{
        background: 'transparent',
        border: '1px solid rgba(255,255,255,.15)',
        color: 'inherit',
        borderRadius: 12,
        padding: '6px 10px',
        cursor: 'pointer',
      }}
    >
      {mode === 'light' ? '☀️ Light' : '🌙 Dark'}
    </button>
  );
}

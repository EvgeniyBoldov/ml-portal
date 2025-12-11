import React, { useState, useRef, useEffect } from 'react';
import { useTheme, type Theme } from '@app/providers/ThemeProvider';
import styles from './ThemeSwitch.module.css';

const SunIcon = () => (
  <svg className={styles.icon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2" />
    <path d="M12 20v2" />
    <path d="m4.93 4.93 1.41 1.41" />
    <path d="m17.66 17.66 1.41 1.41" />
    <path d="M2 12h2" />
    <path d="M20 12h2" />
    <path d="m6.34 17.66-1.41 1.41" />
    <path d="m19.07 4.93-1.41 1.41" />
  </svg>
);

const MoonIcon = () => (
  <svg className={styles.icon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
  </svg>
);

const MonitorIcon = () => (
  <svg className={styles.icon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect width="20" height="14" x="2" y="3" rx="2" />
    <line x1="8" x2="16" y1="21" y2="21" />
    <line x1="12" x2="12" y1="17" y2="21" />
  </svg>
);

interface ThemeSwitchProps {
  showLabel?: boolean;
  variant?: 'button' | 'dropdown';
}

export default function ThemeSwitch({ showLabel = false, variant = 'button' }: ThemeSwitchProps) {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  if (variant === 'button') {
    return (
      <button
        className={styles.button}
        onClick={toggleTheme}
        aria-label="Переключить тему"
        title={resolvedTheme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
      >
        {resolvedTheme === 'dark' ? <MoonIcon /> : <SunIcon />}
      </button>
    );
  }

  const options: { value: Theme; label: string; icon: React.ReactNode }[] = [
    { value: 'light', label: 'Светлая', icon: <SunIcon /> },
    { value: 'dark', label: 'Тёмная', icon: <MoonIcon /> },
    { value: 'system', label: 'Системная', icon: <MonitorIcon /> },
  ];

  return (
    <div className={styles.dropdown} ref={ref}>
      <button
        className={styles.button}
        onClick={() => setOpen(!open)}
        aria-label="Выбрать тему"
        aria-expanded={open}
      >
        {resolvedTheme === 'dark' ? <MoonIcon /> : <SunIcon />}
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          {options.map((opt) => (
            <button
              key={opt.value}
              className={`${styles.menuItem} ${theme === opt.value ? styles.active : ''}`}
              onClick={() => {
                setTheme(opt.value);
                setOpen(false);
              }}
              role="menuitem"
            >
              <span className={styles.menuItemIcon}>{opt.icon}</span>
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

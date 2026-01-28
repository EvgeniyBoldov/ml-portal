import React, { useState } from 'react';
import { useAuth } from '@shared/hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import styles from './Login.module.css';

// Simple inline SVG icons
const BrainIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/>
    <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/>
  </svg>
);

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

const AlertIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
    <circle cx="12" cy="12" r="10"/>
    <line x1="12" y1="8" x2="12" y2="12"/>
    <line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
);

const LayersIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="14" height="14">
    <path d="M12 2L2 7l10 5 10-5-10-5z"/>
    <path d="M2 17l10 5 10-5"/>
    <path d="M2 12l10 5 10-5"/>
  </svg>
);

export default function Login() {
  const nav = useNavigate();
  const { login, loading } = useAuth();
  const [form, setForm] = useState({ login: '', password: '' });
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(form.login, form.password);
      nav('/gpt/chat');
    } catch (e: any) {
      setError(e.message || 'Неверный логин или пароль');
    }
  }

  return (
    <div className={styles.page}>
      {/* Left side - Hero */}
      <div className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroIcon}>
            <BrainIcon />
          </div>
          <h1 className={styles.heroTitle}>Почемучка</h1>
          <p className={styles.heroSubtitle}>
            Единая платформа для работы с AI-ассистентами, базами знаний и интеллектуальным поиском
          </p>
          <div className={styles.features}>
            <div className={styles.feature}>
              <span className={styles.featureIcon}><CheckIcon /></span>
              <span>Чат с AI-ассистентами</span>
            </div>
            <div className={styles.feature}>
              <span className={styles.featureIcon}><CheckIcon /></span>
              <span>RAG — поиск по документам</span>
            </div>
            <div className={styles.feature}>
              <span className={styles.featureIcon}><CheckIcon /></span>
              <span>Управление базами знаний</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Form */}
      <div className={styles.formSide}>
        <div className={styles.formContainer}>
          <div className={styles.formHeader}>
            <div className={styles.logo}>
              <div className={styles.logoIcon}>
                <BrainIcon />
              </div>
              <span className={styles.logoText}>Почемучка</span>
            </div>
            <h2 className={styles.formTitle}>Добро пожаловать</h2>
            <p className={styles.formSubtitle}>Войдите в свой аккаунт для продолжения</p>
          </div>

          <form className={styles.form} onSubmit={onSubmit}>
            <div className={styles.inputGroup}>
              <label className={styles.inputLabel}>Логин</label>
              <Input
                placeholder="Введите логин"
                value={form.login}
                onChange={e => setForm(f => ({ ...f, login: e.target.value }))}
                autoComplete="username"
                autoFocus
              />
            </div>

            <div className={styles.inputGroup}>
              <label className={styles.inputLabel}>Пароль</label>
              <Input
                type="password"
                placeholder="Введите пароль"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className={styles.error}>
                <AlertIcon />
                {error}
              </div>
            )}

            <Button 
              type="submit" 
              disabled={loading || !form.login || !form.password}
              className={styles.submitBtn}
            >
              {loading ? 'Вход...' : 'Войти'}
            </Button>
          </form>

          <div className={styles.footer}>
            <a 
              href="https://boldov.dev" 
              target="_blank" 
              rel="noopener noreferrer"
              className={styles.footerLink}
            >
              <span className={styles.footerIcon}><LayersIcon /></span>
              Boldov Development Ltd
            </a>
            <span className={styles.footerDivider}>•</span>
            <span className={styles.footerYear}>© {new Date().getFullYear()}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

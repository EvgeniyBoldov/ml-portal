import React, { useState } from 'react'
import { useAuth } from '@app/store/auth'
import { useNavigate } from 'react-router-dom'
import Button from '@shared/ui/Button'
import Input from '@shared/ui/Input'
import Card from '@shared/ui/Card'
import styles from './Login.module.css'

export default function Login() {
  const nav = useNavigate()
  const { login, loading } = useAuth()
  const [form, setForm] = useState({ login: '', password: '' })
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await login(form.login, form.password)
      nav('/gpt/chat')
    } catch (e: any) {
      setError(e.message || 'Ошибка входа')
    }
  }
  return (
    <div className={styles.wrap}>
      <Card className={styles.card}>
        <h1>Войти</h1>
        <form className="stack" onSubmit={onSubmit}>
          <label>Логин</label>
          <Input placeholder="user" value={form.login} onChange={e=>setForm(f=>({ ...f, login:e.target.value }))} />
          <label>Пароль</label>
          <Input type="password" placeholder="••••••••" value={form.password} onChange={e=>setForm(f=>({ ...f, password:e.target.value }))} />
          {error && <div className={styles.error}>{error}</div>}
          <Button type="submit" disabled={loading}>{loading ? '…' : 'Войти'}</Button>
        </form>
      </Card>
    </div>
  )
}

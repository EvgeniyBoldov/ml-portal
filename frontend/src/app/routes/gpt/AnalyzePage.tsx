import React, { useEffect, useRef, useState } from 'react'
import Card from '@shared/ui/Card'
import Input from '@shared/ui/Input'
import Button from '@shared/ui/Button'
import Badge from '@shared/ui/Badge'
import * as analyze from '@shared/api/analyze'
import styles from './AnalyzePage.module.css'

type Task = { id: string; source?: string; status: string; result?: string; created_at?: string }

export default function AnalyzePage() {
  const [items, setItems] = useState<Task[]>([])
  const [busy, setBusy] = useState(false)
  const [url, setUrl] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    const res = await analyze.listAnalyze()
    setItems(res.items || [])
  }
  useEffect(() => { refresh(); const t=setInterval(refresh,1500); return ()=>clearInterval(t) }, [])

  async function submitUrl() {
    if (!url.trim()) return
    setBusy(true)
    try {
      await analyze.createAnalyze({ url })
      setUrl('')
      await refresh()
    } finally { setBusy(false) }
  }

  async function submitFile(file: File) {
    setBusy(true)
    try {
      await analyze.createAnalyze({ file })
      await refresh()
    } finally { setBusy(false) }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) submitFile(f)
  }

  return (
    <div className={styles.wrap}>
      <Card className={styles.up}>
        <div className="controls">
          <Input placeholder="Вставьте URL для анализа…" value={url} onChange={e=>setUrl(e.target.value)} className="w-100" />
          <Button onClick={submitUrl} disabled={busy || !url.trim()}>Запустить</Button>
        </div>
        <div className={styles.drop} onDragOver={e=>e.preventDefault()} onDrop={onDrop}>
          <div className="muted">или перетащите файл сюда</div>
          <div>
            <input ref={fileRef} type="file" hidden onChange={e=>{ const f=e.target.files?.[0]; if (f) submitFile(f) }} />
            <Button onClick={()=>fileRef.current?.click()} variant="ghost">Выбрать файл</Button>
          </div>
        </div>
      </Card>

      <Card>
        <table className="table">
          <thead><tr><th>ID</th><th>Источник</th><th>Статус</th><th>Результат</th><th>Создано</th></tr></thead>
          <tbody>
            {items.map(t => (
              <tr key={t.id}>
                <td>{t.id}</td>
                <td className="muted">{t.source || '—'}</td>
                <td><Badge tone={t.status==='done'?'success':t.status==='error'?'danger':t.status==='processing'?'warn':'neutral'}>{t.status}</Badge></td>
                <td>{t.result ? <pre style={{whiteSpace:'pre-wrap'}}>{t.result}</pre> : <span className="muted">—</span>}</td>
                <td className="muted">{t.created_at || '—'}</td>
              </tr>
            ))}
            {items.length===0 && <tr><td colSpan={5} className="muted">Задач пока нет</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

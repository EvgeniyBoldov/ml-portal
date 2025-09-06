import React, { useEffect, useState, useRef } from 'react'
import Card from '@shared/ui/Card'
import Input from '@shared/ui/Input'
import Button from '@shared/ui/Button'
import Badge from '@shared/ui/Badge'
import * as rag from '@shared/api/rag'
import styles from './RagPage.module.css'

type Doc = { id: string; name: string; status: string; tags?: string[]; created_at?: string }

export default function RagPage() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<string>('')
  const [items, setItems] = useState<Doc[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function load(reset=false) {
    setBusy(true)
    try {
      const { items, next_cursor } = await rag.listDocs({ q, status, cursor: reset ? undefined : cursor || undefined })
      setItems(prev => reset ? items : [...prev, ...items])
      setCursor(next_cursor || null)
    } finally { setBusy(false) }
  }

  useEffect(() => { load(true) }, [q, status])

  async function onUpload(file: File) {
    setBusy(true)
    try {
      await rag.uploadFile(file, file.name)
      await load(true)
    } finally { setBusy(false) }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f) onUpload(f)
  }

  return (
    <div className={styles.wrap}>
      <Card className={styles.controls}>
        <div className="controls">
          <Input placeholder="Search…" value={q} onChange={e=>setQ(e.target.value)} />
          <select value={status} onChange={e=>setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="ready">ready</option>
            <option value="processing">processing</option>
            <option value="uploaded">uploaded</option>
            <option value="error">error</option>
          </select>
          <Button onClick={()=>load(true)} disabled={busy}>Refresh</Button>
        </div>
      </Card>

      <div className={styles.grid}>
        <Card className={styles.uploader} onDragOver={e=>e.preventDefault()} onDrop={onDrop}>
          <div className="stack">
            <div className="muted">Drag & drop файл сюда</div>
            <div>или</div>
            <div>
              <input ref={fileRef} type="file" hidden onChange={e=>{ const f=e.target.files?.[0]; if (f) onUpload(f) }} />
              <Button onClick={()=>fileRef.current?.click()}>Выбрать файл</Button>
            </div>
          </div>
        </Card>

        <Card className={styles.tableWrap}>
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Status</th><th>Tags</th><th>Created</th></tr>
            </thead>
            <tbody>
              {items.map(doc => (
                <tr key={doc.id}>
                  <td>{doc.name}</td>
                  <td>
                    <Badge tone={doc.status==='ready'?'success':doc.status==='processing'?'warn':doc.status==='error'?'danger':'neutral'}>{doc.status}</Badge>
                  </td>
                  <td>{(doc.tags || []).join(', ')}</td>
                  <td className="muted">{doc.created_at || '—'}</td>
                </tr>
              ))}
              {items.length === 0 && !busy && <tr><td colSpan={4} className="muted">Нет документов</td></tr>}
            </tbody>
          </table>
          {cursor && <div className={styles.more}><Button variant="ghost" onClick={()=>load(false)} disabled={busy}>Load more</Button></div>}
        </Card>
      </div>
    </div>
  )
}

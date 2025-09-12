import React, { useEffect, useMemo, useState } from 'react'
import Card from '@shared/ui/Card'
import Input from '@shared/ui/Input'
import Button from '@shared/ui/Button'
import Badge from '@shared/ui/Badge'
import Modal from '@shared/ui/Modal'
import Popover from '@shared/ui/Popover'
import { FilterIcon } from '@shared/ui/Icon'
import Select from '@shared/ui/Select'
import FilePicker from '@shared/ui/FilePicker'
import * as analyze from '@shared/api/analyze'
import styles from './AnalyzePage.module.css'

type Task = { id: string; source?: string; status: string; result?: string; created_at?: string }
type ColKey = keyof Pick<Task, 'source'|'status'|'result'|'created_at'>

export default function AnalyzePage() {
  const [items, setItems] = useState<Task[]>([])
  const [busy, setBusy] = useState(false)

  const [q, setQ] = useState('')
  const [filters, setFilters] = useState<Partial<Record<ColKey, string>>>({})
  const [pop, setPop] = useState<{ open: boolean, col?: ColKey, anchor?: {x:number,y:number} }>({ open: false })

  const [openAdd, setOpenAdd] = useState(false)
  const [file, setFile] = useState<File | null>(null)

  async function refresh() {
    const res = await analyze.listAnalyze()
    setItems(res.items || [])
  }

  // Мягкий пуллинг (экспоненциальный backoff)
  useEffect(() => {
    let cancelled = false
    let delay = 1500
    const tick = async () => {
      while (!cancelled) {
        try { await refresh() } catch {}
        await new Promise(r => setTimeout(r, delay))
        delay = Math.min(delay * 2, 10000)
      }
    }
    tick()
    return () => { cancelled = true }
  }, [])

  const rows = useMemo(() => {
    return (items||[]).filter(t => {
      const text = ((t.source||'') + ' ' + (t.result||'') + ' ' + (t.created_at||'') + ' ' + t.status).toLowerCase()
      if (q.trim() && !text.includes(q.toLowerCase())) return false
      if (filters.source && !(t.source||'').toLowerCase().includes((filters.source||'').toLowerCase())) return false
      if (filters.status && t.status !== filters.status) return false
      if (filters.result && !(t.result||'').toLowerCase().includes((filters.result||'').toLowerCase())) return false
      if (filters.created_at && !(t.created_at||'').toLowerCase().includes((filters.created_at||'').toLowerCase())) return false
      return true
    })
  }, [items, q, filters])

  function openFilter(col: ColKey, el: HTMLElement) {
    const r = el.getBoundingClientRect()
    setPop({ open: true, col, anchor: { x: r.left, y: r.bottom + 6 } })
  }
  function clearAll() { setFilters({}); setPop({ open:false }) }

  async function doUpload() {
    if (!file) return
    setBusy(true)
    try {
      await analyze.uploadAnalysisFile(file)
      setOpenAdd(false)
      setFile(null)
      await refresh()
    } finally { setBusy(false) }
  }

  const hasAnyFilter = Object.values(filters).some(Boolean)

  return (
    <div className={styles.wrap}>
      <Card className={styles.card}>
        <div className={styles.header}>
          <div className={styles.title}>Анализ документов — задачи</div>
          <div className={styles.controls}>
            <Input className={styles.search} placeholder="Поиск…" value={q} onChange={e=>setQ(e.target.value)} />
            {hasAnyFilter && <Badge onClick={clearAll}>Сбросить фильтры</Badge>}
            <Button onClick={()=>setOpenAdd(true)}>Добавить</Button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className="table">
            <thead>
              <tr>
                <th>Источник <button className="icon" type="button" aria-label="Фильтр по источнику" onClick={(e)=>openFilter('source', e.currentTarget)}><FilterIcon/></button></th>
                <th>Статус <button className="icon" type="button" aria-label="Фильтр по статусу" onClick={(e)=>openFilter('status', e.currentTarget)}><FilterIcon/></button></th>
                <th>Результат <button className="icon" type="button" aria-label="Фильтр по результату" onClick={(e)=>openFilter('result', e.currentTarget)}><FilterIcon/></button></th>
                <th>Создано <button className="icon" type="button" aria-label="Фильтр по дате создания" onClick={(e)=>openFilter('created_at', e.currentTarget)}><FilterIcon/></button></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td className="muted">{t.source || '—'}</td>
                  <td><Badge tone={t.status==='done'?'success':t.status==='error'?'danger':t.status==='processing'?'warn':'neutral'}>{t.status}</Badge></td>
                  <td style={{maxWidth:480, whiteSpace:'nowrap', textOverflow:'ellipsis', overflow:'hidden'}}>{t.result || '—'}</td>
                  <td className="muted">{t.created_at || '—'}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={4} className="muted">Нет записей</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={openAdd} onClose={()=>setOpenAdd(false)} title="Новый анализ"
        footer={<><Button variant="ghost" onClick={()=>setOpenAdd(false)}>Отмена</Button><Button onClick={doUpload} disabled={busy || !file}>Запустить</Button></>}>
        <FilePicker onFileSelected={setFile} />
      </Modal>

      <Popover 
        trigger={<div />}
        content={
          <div className="stack" style={{minWidth: 260}}>
          {pop.col === 'status' ? (
            <Select
              value={filters.status || ''}
              onChange={e=>setFilters(f=>({ ...f, status: (e.target as HTMLSelectElement).value || undefined }))}
            >
              <option value="">Любой</option>
              <option value="queued">queued</option>
              <option value="processing">processing</option>
              <option value="done">done</option>
              <option value="error">error</option>
            </Select>
          ) : (
            <Input placeholder="Фильтр…" value={(filters[pop.col as ColKey] || '') as string} onChange={e=>{
              const val = e.target.value
              const col = pop.col as ColKey
              setFilters(f=>({ ...f, [col]: (val || '').trim() || undefined }))
            }} />
          )}
          <div style={{display:'flex', gap:8, justifyContent:'space-between'}}>
            <Button size="sm" variant="ghost" onClick={()=>{ const col = pop.col as ColKey; setFilters(f=>({ ...f, [col]: undefined })); }}>Очистить</Button>
            <Button size="sm" onClick={()=>setPop({open:false})}>Применить</Button>
          </div>
          </div>
        }
        align="end"
      />
    </div>
  )
}

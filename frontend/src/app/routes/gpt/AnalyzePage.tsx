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
  useEffect(() => { refresh(); const t=setInterval(refresh,1500); return ()=>clearInterval(t) }, [])

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
      await analyze.createAnalyze({ file })
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
            {hasAnyFilter && <Button size="sm" variant="ghost" onClick={clearAll}>Reset filters</Button>}
            <Input className={styles.search} placeholder="🔎 Search…" value={q} onChange={e=>setQ(e.target.value)} />
            <Button onClick={()=>setOpenAdd(true)}>Add</Button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className="table">
            <thead>
              <tr>
                <th><span className="clickable" onClick={(e)=>openFilter('source', e.currentTarget as any)}>Source <FilterIcon active={!!filters.source} /></span></th>
                <th><span className="clickable" onClick={(e)=>openFilter('status', e.currentTarget as any)}>Status <FilterIcon active={!!filters.status} /></span></th>
                <th><span className="clickable" onClick={(e)=>openFilter('result', e.currentTarget as any)}>Result <FilterIcon active={!!filters.result} /></span></th>
                <th><span className="clickable" onClick={(e)=>openFilter('created_at', e.currentTarget as any)}>Created <FilterIcon active={!!filters.created_at} /></span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(t => (
                <tr key={t.id}>
                  <td className="muted">{t.source || '—'}</td>
                  <td><Badge tone={t.status==='done'?'success':t.status==='error'?'danger':t.status==='processing'?'warn':'neutral'}>{t.status}</Badge></td>
                  <td>{t.result ? <pre style={{whiteSpace:'pre-wrap', margin:0}}>{t.result}</pre> : <span className="muted">—</span>}</td>
                  <td className="muted">{t.created_at || '—'}</td>
                </tr>
              ))}
              {rows.length===0 && <tr><td colSpan={4} className="muted">Задач пока нет</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={openAdd} onClose={()=>{setOpenAdd(false); setFile(null)}} title="Upload for analyze" size="half"
        footer={<>
          <Button variant="ghost" onClick={()=>{setOpenAdd(false); setFile(null)}}>Cancel</Button>
          <Button onClick={doUpload} disabled={!file || busy}>Upload</Button>
        </>}>
        <div className="stack">
          <FilePicker onFileSelected={setFile} />
          <div className="muted">{file ? `Selected: ${file.name}` : 'Choose a file to upload'}</div>
        </div>
      </Modal>

      <Popover open={pop.open} anchor={pop.anchor || null} onClose={()=>setPop({open:false})} title="Filter">
        {pop.col === 'source' && (
          <Input autoFocus placeholder="contains…" value={filters.source||''} onChange={e=>setFilters(f=>({...f, source: e.target.value||undefined}))} />
        )}
        {pop.col === 'status' && (
          <Select value={filters.status||''} onChange={e=>setFilters(f=>({...f, status: (e.target as HTMLSelectElement).value || undefined}))}>
            <option value="">all</option>
            <option value="queued">queued</option>
            <option value="processing">processing</option>
            <option value="done">done</option>
            <option value="error">error</option>
          </Select>
        )}
        {pop.col === 'result' && (
          <Input placeholder="contains…" value={filters.result||''} onChange={e=>setFilters(f=>({...f, result: e.target.value||undefined}))} />
        )}
        {pop.col === 'created_at' && (
          <Input placeholder="YYYY-MM…" value={filters.created_at||''} onChange={e=>setFilters(f=>({...f, created_at: e.target.value||undefined}))} />
        )}
        <div style={{display:'flex', justifyContent:'end', gap:8, marginTop:8}}>
          <Button size="sm" variant="ghost" onClick={()=>{ if(pop.col) setFilters(f=>({...f, [pop.col!]: undefined})); }}>Clear</Button>
          <Button size="sm" onClick={()=>setPop({open:false})}>Apply</Button>
        </div>
      </Popover>
    </div>
  )
}

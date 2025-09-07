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
import * as rag from '@shared/api/rag'
import styles from './RagPage.module.css'

type Doc = { id: string; name: string; status: string; tags?: string[]; created_at?: string }
type ColKey = keyof Pick<Doc, 'name'|'status'|'tags'|'created_at'>

export default function RagPage() {
  const [items, setItems] = useState<Doc[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [q, setQ] = useState('')
  const [filters, setFilters] = useState<Partial<Record<ColKey, string>>>({})
  const [pop, setPop] = useState<{ open: boolean, col?: ColKey, anchor?: {x:number,y:number} }>({ open: false })

  const [openAdd, setOpenAdd] = useState(false)
  const [file, setFile] = useState<File | null>(null)

  async function load(reset=false) {
    setBusy(true)
    try {
      const { items, next_cursor } = await rag.listDocs({ cursor: reset? undefined : cursor || undefined })
      setItems(prev => reset ? items : [...prev, ...items])
      setCursor(next_cursor || null)
    } finally { setBusy(false) }
  }
  useEffect(() => { load(true) }, [])

  const rows = useMemo(() => {
    return items.filter(d => {
      const text = (d.name + ' ' + (d.tags || []).join(' ') + ' ' + (d.created_at || '') + ' ' + d.status).toLowerCase()
      if (q.trim() && !text.includes(q.toLowerCase())) return false
      if (filters.name && !d.name.toLowerCase().includes(filters.name.toLowerCase())) return false
      if (filters.status && d.status !== filters.status) return false
      if (filters.tags && !(d.tags || []).join(',').toLowerCase().includes((filters.tags||'').toLowerCase())) return false
      if (filters.created_at && !(d.created_at || '').toLowerCase().includes((filters.created_at||'').toLowerCase())) return false
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
      await rag.uploadFile(file, file.name)
      setOpenAdd(false)
      setFile(null)
      await load(true)
    } finally { setBusy(false) }
  }

  const hasAnyFilter = Object.values(filters).some(Boolean)

  return (
    <div className={styles.wrap}>
      <Card className={styles.card}>
        <div className={styles.header}>
          <div className={styles.title}>База знаний — документы</div>
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
                <th>Документ <button className="icon" type="button" aria-label="Фильтр по документу" onClick={(e)=>openFilter('name', e.currentTarget)}><FilterIcon/></button></th>
                <th>Статус <button className="icon" type="button" aria-label="Фильтр по статусу" onClick={(e)=>openFilter('status', e.currentTarget)}><FilterIcon/></button></th>
                <th>Теги <button className="icon" type="button" aria-label="Фильтр по тегам" onClick={(e)=>openFilter('tags', e.currentTarget)}><FilterIcon/></button></th>
                <th>Создано <button className="icon" type="button" aria-label="Фильтр по дате создания" onClick={(e)=>openFilter('created_at', e.currentTarget)}><FilterIcon/></button></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(doc => (
                <tr key={doc.id}>
                  <td>{doc.name}</td>
                  <td><Badge tone={doc.status==='ready'?'success':doc.status==='processing'?'warn':doc.status==='error'?'danger':'neutral'}>{doc.status}</Badge></td>
                  <td>{(doc.tags || []).join(', ') || '—'}</td>
                  <td className="muted">{doc.created_at || '—'}</td>
                </tr>
              ))}
              {rows.length===0 && !busy && <tr><td colSpan={4} className="muted">Нет документов</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={openAdd} onClose={()=>{setOpenAdd(false); setFile(null)}} title="Новый документ" size="half"
        footer={<>
          <Button variant="ghost" onClick={()=>{setOpenAdd(false); setFile(null)}}>Отмена</Button>
          <Button onClick={doUpload} disabled={!file || busy}>Загрузить</Button>
        </>}>
        <div className="stack">
          <FilePicker onFileSelected={setFile} />
          <div className="muted">{file ? `Выбрано: ${file.name}` : 'Выберите файл для загрузки'}</div>
        </div>
      </Modal>

      <Popover open={pop.open} anchor={pop.anchor || null} onClose={()=>setPop({open:false})}>
        {pop.col === 'name' && (
          <Input autoFocus placeholder="содержит…" value={filters.name||''} onChange={e=>setFilters(f=>({ ...f, name: e.target.value||undefined }))} />
        )}
        {pop.col === 'status' && (
          <Select value={filters.status||''} onChange={e=>setFilters(f=>({ ...f, status: (e.target as HTMLSelectElement).value || undefined }))}>
            <option value="">любой</option>
            <option value="uploaded">uploaded</option>
            <option value="normalizing">normalizing</option>
            <option value="chunking">chunking</option>
            <option value="embedding">embedding</option>
            <option value="indexing">indexing</option>
            <option value="ready">ready</option>
            <option value="archived">archived</option>
            <option value="deleting">deleting</option>
            <option value="error">error</option>
          </Select>
        )}
        {pop.col === 'tags' && (
          <Input placeholder="содержит…" value={filters.tags||''} onChange={e=>setFilters(f=>({ ...f, tags: e.target.value||undefined }))} />
        )}
        {pop.col === 'created_at' && (
          <Input placeholder="YYYY-MM…" value={filters.created_at||''} onChange={e=>setFilters(f=>({ ...f, created_at: e.target.value||undefined }))} />
        )}
        <div style={{display:'flex', justifyContent:'end', gap:8, marginTop:8}}>
          <Button size="sm" variant="ghost" onClick={()=>{ if(pop.col) setFilters(f=>({ ...f, [pop.col!]: undefined })); }}>Очистить</Button>
          <Button size="sm" onClick={()=>setPop({open:false})}>Применить</Button>
        </div>
      </Popover>
    </div>
  )
}

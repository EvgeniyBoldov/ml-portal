import React, { useEffect, useMemo, useState } from 'react'
import Card from '@shared/ui/Card'
import Input from '@shared/ui/Input'
import Button from '@shared/ui/Button'
import Badge from '@shared/ui/Badge'
import Modal from '@shared/ui/Modal'
import Popover from '@shared/ui/Popover'
import { FilterIcon, MoreVerticalIcon, DownloadIcon, RefreshIcon, ArchiveIcon, TrashIcon } from '@shared/ui/Icon'
import Select from '@shared/ui/Select'
import FilePicker from '@shared/ui/FilePicker'
import * as rag from '@shared/api/rag'
import { RagDocument } from '@shared/api/types'
import styles from './Rag.module.css'

type ColKey = 'name' | 'status' | 'created_at' | 'tags'

export default function Rag() {
  const [items, setItems] = useState<RagDocument[]>([])
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')
  const [filters, setFilters] = useState<Partial<Record<ColKey, string>>>({})
  const [pop, setPop] = useState<{ open: boolean, col?: ColKey, anchor?: {x:number,y:number} }>({ open: false })
  const [openAdd, setOpenAdd] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [uploadTags, setUploadTags] = useState<string[]>([])
  const [selectedDoc, setSelectedDoc] = useState<RagDocument | null>(null)
  const [actionMenuOpen, setActionMenuOpen] = useState(false)

  async function refresh() {
    const res = await rag.listDocs({ page: 1, size: 100 })
    setItems(res.items || [])
  }

  useEffect(() => {
    refresh()
  }, [])

  const rows = useMemo(() => {
    return (items||[]).filter(t => {
      const text = ((t.name||'') + ' ' + (t.status||'') + ' ' + (t.created_at||'') + ' ' + (t.tags?.join(' ')||'')).toLowerCase()
      if (q.trim() && !text.includes(q.toLowerCase())) return false
      if (filters.name && !(t.name||'').toLowerCase().includes((filters.name||'').toLowerCase())) return false
      if (filters.status && t.status !== filters.status) return false
      if (filters.tags && !(t.tags?.join(' ')||'').toLowerCase().includes((filters.tags||'').toLowerCase())) return false
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
      await rag.uploadFile(file, file.name, uploadTags)
      setOpenAdd(false)
      setFile(null)
      setUploadTags([])
      await refresh()
    } finally { setBusy(false) }
  }

  const handleDownload = async (doc: RagDocument, kind: 'original' | 'canonical' = 'original') => {
    try {
      const res = await rag.downloadRagFile(doc.id, kind)
      if (res.url) {
        window.open(res.url, '_blank')
      }
    } catch (error) {
      console.error('Download failed:', error)
    }
  }

  const handleArchive = async (doc: RagDocument) => {
    try {
      await rag.archiveRagDocument(doc.id)
      await refresh()
    } catch (error) {
      console.error('Archive failed:', error)
    }
  }

  const handleDelete = async (doc: RagDocument) => {
    if (!confirm('Удалить документ?')) return
    try {
      await rag.deleteRagDocument(doc.id)
      await refresh()
    } catch (error) {
      console.error('Delete failed:', error)
    }
  }

  const handleReindex = async (doc: RagDocument) => {
    if (!confirm('Переиндексировать документ?')) return
    try {
      // TODO: Добавить API для переиндексации
      alert('Функция переиндексации будет добавлена')
    } catch (error) {
      console.error('Reindex failed:', error)
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'queued': return 'В очереди'
      case 'processing': return 'Обработка'
      case 'ready': return 'Готов'
      case 'error': return 'Ошибка'
      case 'archived': return 'Архив'
      default: return status
    }
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
                <th>Название <button className="icon" type="button" aria-label="Фильтр по названию" onClick={(e)=>openFilter('name', e.currentTarget)}><FilterIcon/></button></th>
                <th>Статус <button className="icon" type="button" aria-label="Фильтр по статусу" onClick={(e)=>openFilter('status', e.currentTarget)}><FilterIcon/></button></th>
                <th>Теги <button className="icon" type="button" aria-label="Фильтр по тегам" onClick={(e)=>openFilter('tags', e.currentTarget)}><FilterIcon/></button></th>
                <th>Создано <button className="icon" type="button" aria-label="Фильтр по дате создания" onClick={(e)=>openFilter('created_at', e.currentTarget)}><FilterIcon/></button></th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td className="muted">{t.name || '—'}</td>
                  <td><Badge tone={t.status==='ready'?'success':t.status==='error'?'danger':t.status==='processing'?'warn':'neutral'}>{getStatusText(t.status)}</Badge></td>
                  <td>{t.tags?.join(', ') || '—'}</td>
                  <td className="muted">{t.created_at || '—'}</td>
                  <td>
                    <Popover
                      trigger={
                        <button 
                          className="icon" 
                          type="button" 
                          aria-label="Действия"
                          onClick={() => {
                            setSelectedDoc(t)
                            setActionMenuOpen(true)
                          }}
                        >
                          <MoreVerticalIcon/>
                        </button>
                      }
                      content={
                        <div className="stack" style={{minWidth: 180}}>
                          {t.status === 'ready' && (
                            <>
                              <Button size="sm" variant="ghost" onClick={() => handleDownload(t, 'original')}>
                                <span style={{marginRight: 6, display: 'inline-flex', alignItems: 'center'}}>
                                  <DownloadIcon size={12}/>
                                </span>
                                Скачать документ
                              </Button>
                              {t.url_canonical_file && (
                                <Button size="sm" variant="ghost" onClick={() => handleDownload(t, 'canonical')}>
                                  <span style={{marginRight: 6, display: 'inline-flex', alignItems: 'center'}}>
                                    <DownloadIcon size={12}/>
                                  </span>
                                  Скачать канонический вид
                                </Button>
                              )}
                              <Button size="sm" variant="ghost" onClick={() => handleReindex(t)}>
                                <span style={{marginRight: 6, display: 'inline-flex', alignItems: 'center'}}>
                                  <RefreshIcon size={12}/>
                                </span>
                                Пересчитать
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => handleArchive(t)}>
                                <span style={{marginRight: 6, display: 'inline-flex', alignItems: 'center'}}>
                                  <ArchiveIcon size={12}/>
                                </span>
                                Заархивировать
                              </Button>
                            </>
                          )}
                          <Button size="sm" variant="ghost" onClick={() => handleDelete(t)}>
                            <span style={{marginRight: 6, display: 'inline-flex', alignItems: 'center'}}>
                              <TrashIcon size={12}/>
                            </span>
                            Удалить
                          </Button>
                        </div>
                      }
                      align="end"
                    />
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={5} className="muted">Нет записей</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={openAdd} onClose={()=>setOpenAdd(false)} title="Новый документ"
        footer={<><Button variant="ghost" onClick={()=>setOpenAdd(false)}>Отмена</Button><Button onClick={doUpload} disabled={busy || !file}>Загрузить</Button></>}>
        <div className="stack">
          <FilePicker onFileSelected={setFile} accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt" />
          <div>
            <label>Теги (опционально):</label>
            <Input 
              placeholder="Введите теги через запятую..." 
              value={uploadTags.join(', ')} 
              onChange={e => setUploadTags(e.target.value.split(',').map(t => t.trim()).filter(Boolean))} 
            />
          </div>
        </div>
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
              <option value="queued">В очереди</option>
              <option value="processing">Обработка</option>
              <option value="ready">Готов</option>
              <option value="error">Ошибка</option>
              <option value="archived">Архив</option>
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

import React, { useEffect, useState } from 'react'
import styles from './ChatSidebar.module.css'
import Button from '@shared/ui/Button'
import * as chats from '@shared/api/chats'
import { useNavigate, useParams } from 'react-router-dom'
import Modal from '@shared/ui/Modal'
import Input from '@shared/ui/Input'

type Item = { id: string; name?: string }

export default function ChatSidebar() {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [renameId, setRenameId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteId, setDeleteId] = useState<string | null>(null)

  const nav = useNavigate()
  const { chatId } = useParams()

  async function refresh() {
    setLoading(true)
    try {
      const res = await chats.listChats({ limit: 100 })
      setItems((res.items || []).map((it:any)=>({ id: it.id || it.chat_id || it, name: it.name })))
    } finally { setLoading(false) }
  }

  useEffect(() => { refresh() }, [])

  async function onNew() {
    const { chat_id } = await chats.createChat('Новый чат')
    await refresh()
    nav(`/gpt/chat/${chat_id}`)
  }

  function openRename(it: Item) {
    setRenameId(it.id)
    setRenameValue(it.name || 'Untitled')
  }
  async function doRename() {
    if (!renameId) return
    await chats.renameChat(renameId, renameValue || 'Untitled')
    setRenameId(null)
    await refresh()
  }
  async function doDelete() {
    if (!deleteId) return
    await chats.deleteChat(deleteId)
    setDeleteId(null)
    await refresh()
    if (chatId === deleteId) nav('/gpt/chat')
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.head}>
        <div className={styles.title}>Chats</div>
      </div>
      <div className={styles.list}>
        {/* New chat as a regular item */}
        <div className={styles.row}>
          <button className={styles.item} onClick={onNew} title="+ Новый чат">
            <span className={styles.plus}>+</span>
            <span className={styles.name}>+ Новый чат</span>
          </button>
        </div>

        {loading && <div className={styles.empty}>Loading…</div>}
        {!loading && items.length === 0 && <div className={styles.empty}>No chats yet</div>}
        {items.map(it => (
          <div key={it.id} className={[styles.row, chatId === it.id ? styles.active : ''].join(' ')}>
            <button
              className={styles.item}
              onClick={()=>nav(`/gpt/chat/${it.id}`)}
              title={it.name || it.id}
            >
              <span className={styles.dot} /> <span className={styles.name}>{it.name || 'Untitled'}</span>
            </button>
            <div className={styles.actions}>
              <button className={styles.icon} title="Rename" onClick={()=>openRename(it)}>✎</button>
              <button className={styles.icon} title="Delete" onClick={()=>setDeleteId(it.id)}>🗑</button>
            </div>
          </div>
        ))}
      </div>

      <Modal open={!!renameId} onClose={()=>setRenameId(null)} title="Rename chat"
        footer={<><Button variant="ghost" onClick={()=>setRenameId(null)}>Cancel</Button><Button onClick={doRename}>Save</Button></>}>
        <Input className="w-100" value={renameValue} onChange={e=>setRenameValue(e.target.value)} />
      </Modal>

      <Modal open={!!deleteId} onClose={()=>setDeleteId(null)} title="Delete chat"
        footer={<><Button variant="ghost" onClick={()=>setDeleteId(null)}>Cancel</Button><Button variant="danger" onClick={doDelete}>Delete</Button></>}>
        <div>Удалить чат безвозвратно?</div>
      </Modal>
    </aside>
  )
}

import React, { useMemo, useState } from 'react'
import styles from './ChatSidebar.module.css'
import Button from '@shared/ui/Button'
import { useNavigate, useParams } from 'react-router-dom'
import Modal from '@shared/ui/Modal'
import Input from '@shared/ui/Input'
import Popover from '@shared/ui/Popover'
import { useChat } from '../../contexts/ChatContext'
import ChatTags from '../../components/ChatTags'

function hueFromString(s: string){
  let h = 0
  for (let i=0;i<s.length;i++) h = (h*31 + s.charCodeAt(i)) >>> 0
  return h % 360
}

function KebabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>
}

export default function ChatSidebar() {
  const { chatId } = useParams()
  const nav = useNavigate()
  const { state, createChat, renameChat, deleteChat, updateChatTags, removeChatLocal, restoreChatLocal, deleteChatApiOnly } = useChat()

  const [renameTarget, setRenameTarget] = useState<{ id: string, name: string } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string, name?: string } | null>(null)
  const [pendingUndo, setPendingUndo] = useState<{ id: string, name?: string|null, tags?: string[]|null, secs: number, tid: any, iid: any } | null>(null)
  const [editTagsTarget, setEditTagsTarget] = useState<{ id: string, tags: string[] } | null>(null)

  const chats = useMemo(() => state.chatsOrder.map(id => state.chatsById[id]), [state.chatsOrder, state.chatsById])

  async function onCreate() {
    const id = await createChat('Новый чат')
    nav(`/gpt/chat/${id}`)
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.head}>
        <div className={styles.title}>Чаты</div>
        <Button size="sm" onClick={onCreate}>+ Новый</Button>
      </div>

      <div className={styles.list}>
        {chats.length === 0 && <div className={styles.item} style={{ opacity: .7 }}>Нет чатов</div>}
        {chats.map(chat => (
          <div key={chat.id} className={[styles.row, chatId === chat.id ? styles.active : ''].join(' ')}>
            <button className={styles.item} onClick={() => nav(`/gpt/chat/${chat.id}`)}>
              <div className={styles.name}>{chat.name || 'Без названия'}</div>
              {Array.isArray(chat.tags) && chat.tags.length > 0 && (
                <div className={styles.tags}>
                  {chat.tags.map(tag => {
                  const h = hueFromString(tag)
                  const bg = `hsla(${h}, 70%, 45%, .18)`
                  const bd = `hsla(${h}, 70%, 50%, .45)`
                  const fg = `hsla(${h}, 80%, 80%, .95)`
                  return <span key={tag} className={styles.tag} style={{ background: bg, borderColor: bd, color: fg }}>{tag}</span>
                  })}
                </div>
              )}
            </button>
            <Popover
              trigger={<button className={styles.kebabBtn} aria-label="Меню"><KebabIcon/></button>}
              content={<div className={styles.menu}>
                <button className={styles.item} onClick={() => setRenameTarget({ id: chat.id, name: chat.name || '' })}>Переименовать</button>
                <button className={styles.item} onClick={() => setEditTagsTarget({ id: chat.id, tags: chat.tags || [] })}>Теги…</button>
                <button className={styles.item} onClick={() => setDeleteTarget({ id: chat.id, name: chat.name || '' })}>Удалить</button>
              </div>}
              align="end"
            />
          </div>
        ))}
      </div>

      <Modal open={!!renameTarget} onClose={() => setRenameTarget(null)} title="Переименовать чат"
        footer={<>
          <Button variant="ghost" onClick={() => setRenameTarget(null)}>Отмена</Button>
          <Button onClick={async () => {
            if (!renameTarget) return
            await renameChat(renameTarget.id, renameTarget.name || 'Без названия')
            setRenameTarget(null)
          }}>Сохранить</Button>
        </>}
      >
        <Input value={renameTarget?.name || ''} onChange={e => setRenameTarget(v => v ? { ...v, name: e.target.value } : v)} className="w-100" />
      </Modal>

      <Modal open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title="Удалить чат"
        footer={<>
          <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Отмена</Button>
          <Button variant="danger" onClick={async () => {
            if (!deleteTarget) return
            const chat = state.chatsById[deleteTarget.id]
            // Optimistic remove from state
            // We will call API after countdown unless undone
            const secsTotal = 5
            let secs = secsTotal
            // remove locally
            removeChatLocal(deleteTarget.id)
            if (chatId === deleteTarget.id) nav('/gpt/chat')
            setDeleteTarget(null)

            const tid = setTimeout(async () => {
              try { await deleteChatApiOnly(chat.id) } catch(e){ console.error(e) }
              setPendingUndo(null)
            }, secsTotal*1000)
            const iid = setInterval(() => {
              secs -= 1
              setPendingUndo(v => v ? { ...v, secs } : v)
            }, 1000)
            setPendingUndo({ id: chat.id, name: chat?.name || 'Без названия', tags: chat?.tags || [], secs, tid, iid })
          }}>Удалить</Button>
        </>}
      >
        Вы уверены, что хотите удалить чат «{deleteTarget?.name || 'Без названия'}»?
      </Modal>

      {editTagsTarget && (
        <ChatTags
          chatId={editTagsTarget.id}
          tags={editTagsTarget.tags}
          onTagsChange={async (tags) => {
            await updateChatTags(editTagsTarget.id, tags)
            setEditTagsTarget(null)
          }}
        />
      )}
    {pendingUndo && (
        <div className={styles.undoBar} role="status">
          <div className={styles.undoText}>Чат «{pendingUndo.name}» удалён. Отменить можно в течение {pendingUndo.secs} с.</div>
          <button className={styles.undoBtn} onClick={() => {
            clearTimeout(pendingUndo.tid)
            clearInterval(pendingUndo.iid)
            // restore in local state
            restoreChatLocal({ id: pendingUndo.id, name: pendingUndo.name || null, tags: pendingUndo.tags || [] } as any)
            setPendingUndo(null)
          }}>Отменить</button>
        </div>
      )}
    </aside>
  )
}

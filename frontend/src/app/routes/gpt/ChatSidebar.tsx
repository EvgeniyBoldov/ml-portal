import React, { useState } from 'react'
import styles from './ChatSidebar.module.css'
import Button from '@shared/ui/Button'
import { useNavigate, useParams } from 'react-router-dom'
import Modal from '@shared/ui/Modal'
import Input from '@shared/ui/Input'
import { useChat } from '../../contexts/ChatContext'
import ChatSearch from '../../components/ChatSearch'
import ChatExport from '../../components/ChatExport'
import ChatStats from '../../components/ChatStats'
import ChatTags from '../../components/ChatTags'

export default function ChatSidebar() {
  const [renameId, setRenameId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteId, setDeleteId] = useState<string | null>(null)

  const nav = useNavigate()
  const { chatId } = useParams()
  const { state, createChat, renameChat, deleteChat, updateChatTags } = useChat()

  const { chats, isLoading } = state
  const items = Object.values(chats).sort((a, b) => 
    new Date(b.last_message_at || b.created_at || 0).getTime() - 
    new Date(a.last_message_at || a.created_at || 0).getTime()
  )

  async function onNew() {
    try {
      const chatId = await createChat('Новый чат')
      nav(`/gpt/chat/${chatId}`)
    } catch (error) {
      console.error('Failed to create chat:', error)
    }
  }

  function openRename(chat: { id: string; name?: string }) {
    setRenameId(chat.id)
    setRenameValue(chat.name || 'Untitled')
  }

  async function doRename() {
    if (!renameId) return
    try {
      await renameChat(renameId, renameValue || 'Untitled')
      setRenameId(null)
    } catch (error) {
      console.error('Failed to rename chat:', error)
    }
  }

  async function doDelete() {
    if (!deleteId) return
    try {
      await deleteChat(deleteId)
      setDeleteId(null)
      if (chatId === deleteId) nav('/gpt/chat')
    } catch (error) {
      console.error('Failed to delete chat:', error)
    }
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.head}>
        <div className={styles.title}>Chats</div>
        <ChatExport />
      </div>
      
      <ChatSearch />
      
      <div className={styles.list}>
        {/* New chat as a regular item */}
        <div className={styles.row}>
          <button className={styles.item} onClick={onNew} title="+ Новый чат">
            <span className={styles.plus}>+</span>
            <span className={styles.name}>+ Новый чат</span>
          </button>
        </div>

        {isLoading && <div className={styles.empty}>Loading…</div>}
        {!isLoading && items.length === 0 && <div className={styles.empty}>No chats yet</div>}
        {items.map(chat => (
          <div key={chat.id} className={[styles.row, chatId === chat.id ? styles.active : ''].join(' ')}>
            <button
              className={styles.item}
              onClick={() => {
                nav(`/gpt/chat/${chat.id}`)
              }}
              title={chat.name || chat.id}
            >
              <span className={styles.dot} /> 
              <div className={styles.chatInfo}>
                <span className={styles.name}>{chat.name || 'Untitled'}</span>
                {chat.messages.length > 0 && (
                  <span className={styles.messageCount}>({chat.messages.length})</span>
                )}
                <ChatTags 
                  chatId={chat.id} 
                  tags={chat.tags || []} 
                  onTagsChange={(tags) => {
                    updateChatTags(chat.id, tags)
                  }}
                />
              </div>
            </button>
            <div className={styles.actions}>
              <button className={styles.icon} title="Rename" onClick={() => openRename(chat)}>✎</button>
              <button className={styles.icon} title="Delete" onClick={() => setDeleteId(chat.id)}>🗑</button>
            </div>
          </div>
        ))}
      </div>

      <ChatStats />

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

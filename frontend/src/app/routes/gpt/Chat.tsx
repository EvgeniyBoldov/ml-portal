import React, { useEffect, useRef, useState } from 'react'
import styles from './Chat.module.css'
import Card from '@shared/ui/Card'
import Button from '@shared/ui/Button'
import Textarea from '@shared/ui/Textarea'
import { useNavigate, useParams } from 'react-router-dom'
import { useChat } from '../../contexts/ChatContext'

export default function Chat() {
  const { chatId } = useParams()
  const nav = useNavigate()
  const { state, createChat, loadMessages, sendMessage, sendMessageStream, setCurrentChat } = useChat()
  
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [useRag, setUseRag] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const messagesRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const currentChat = chatId ? state.chats[chatId] : null
  const items = currentChat?.messages || []

  useEffect(() => {
    (async () => {
      if (!chatId) {
        try {
          const newChatId = await createChat('Новый чат')
          nav(`/gpt/chat/${newChatId}`, { replace: true })
        } catch (error) {
          console.error('Failed to create chat:', error)
        }
        return
      }
      
      setCurrentChat(chatId)
      
      // Загружаем сообщения если их нет
      if (!currentChat?.messages.length) {
        await loadMessages(chatId)
      }
    })()
  }, [chatId, createChat, loadMessages, nav, setCurrentChat])

  useEffect(() => {
    // автопрокрутка вниз при новых сообщениях
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' })
  }, [items.length, busy])

  const handleLoadMore = async () => {
    if (!chatId || !currentChat?.hasMore || isLoadingMore) return
    
    setIsLoadingMore(true)
    try {
      await loadMessages(chatId, true)
    } catch (error) {
      console.error('Failed to load more messages:', error)
    } finally {
      setIsLoadingMore(false)
    }
  }

  async function onSend() {
    const content = text.trim()
    if (!content || !chatId) return
    setBusy(true)
    setText('')
    
    try {
      // Пытаемся стримить; если не поддерживается — используем обычный ответ
      let streamed = false
      try {
        await sendMessageStream(chatId, content, useRag)
        streamed = true
      } catch {
        // игнор, попробуем обычный endpoint
      }
      
      if (!streamed) {
        await sendMessage(chatId, content, useRag)
      }
    } catch (error) {
      console.error('Failed to send message:', error)
    } finally {
      setBusy(false)
    }
    taRef.current?.focus()
  }

  return (
    <div className={styles.wrap}>
      <Card className={styles.panel}>
        <div className={styles.messages} ref={messagesRef}>
          {currentChat?.hasMore && (
            <div className={styles.loadMore}>
              <Button 
                onClick={handleLoadMore} 
                disabled={isLoadingMore}
                size="small"
                variant="ghost"
              >
                {isLoadingMore ? 'Загрузка...' : 'Загрузить больше сообщений'}
              </Button>
            </div>
          )}
          
          {items.length === 0 && !currentChat?.isLoading && (
            <div className={styles.empty}>Пока нет сообщений</div>
          )}
          
          {currentChat?.isLoading && items.length === 0 && (
            <div className={styles.empty}>Загрузка сообщений...</div>
          )}
          
          {items.map((m, i) => (
            <div key={m.id || i} className={m.role === 'user' ? styles.user : styles.assistant}>
              <div className={styles.messageContent}>{m.content}</div>
              {m.created_at && (
                <div className={styles.messageTime}>
                  {new Date(m.created_at).toLocaleTimeString()}
                </div>
              )}
            </div>
          ))}
          
          {busy && <div className={[styles.assistant, styles.typing].join(' ')}>…</div>}
        </div>
        <div className={styles.composer}>
          <div className={styles.inputArea}>
            <Textarea
              ref={taRef}
              placeholder="Спросите что-нибудь… (Ctrl/⌘+Enter — отправить)"
              value={text}
              onChange={e=>setText(e.target.value)}
              onKeyDown={e=>{ if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') onSend() }}
              rows={4}
            />
          </div>
          <div className={styles.controls}>
            <div />
            <div className={styles.actionsBottom}>
              <Button onClick={onSend} disabled={busy || !text.trim()}>Отправить</Button>
              <label className={styles.ragToggle} title="Использовать базу знаний (RAG) при ответе">
                <input type="checkbox" checked={useRag} onChange={e=>setUseRag(e.target.checked)} />
                RAG из БЗ
              </label>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

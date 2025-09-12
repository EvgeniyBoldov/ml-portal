import React, { useEffect, useMemo, useRef, useState } from 'react'
import styles from './Chat.module.css'
import Card from '@shared/ui/Card'
import Button from '@shared/ui/Button'
import Textarea from '@shared/ui/Textarea'
import { useNavigate, useParams } from 'react-router-dom'
import { useChat } from '../../contexts/ChatContext'
import EmptyState from '../../components/EmptyState'

export default function Chat() {
  const { chatId } = useParams()
  const nav = useNavigate()
  const { state, loadMessages, setCurrentChat, sendMessageStream } = useChat()

  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [useRag, setUseRag] = useState(false)
  const [streamText, setStreamText] = useState('')

  const current = useMemo(() => chatId ? state.messagesByChat[chatId] : undefined, [chatId, state.messagesByChat])
  const messages = current?.items || []

  useEffect(() => {
    if (!chatId) return
    setCurrentChat(chatId)
    // load once
    if (!state.messagesByChat[chatId]?.loaded) {
      loadMessages(chatId).catch(console.error)
    }
    // cleanup stream text on chat switch
    setStreamText('')
  }, [chatId])

  if (!chatId) {
    return (
      <div className={styles.main}>
        <EmptyState
          title="Выберите чат"
          description="Слева — список ваших чатов. Создайте новый или откройте существующий."
          action={<Button onClick={() => nav('/gpt/chat')}>Обновить</Button>}
        />
      </div>
    )
  }

  async function onSend() {
    if (!text.trim()) return
    setBusy(true)
    setStreamText('')
    const toSend = text
    setText('')
    try {
      await sendMessageStream(chatId, toSend, (delta) => setStreamText(delta), useRag)
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(false)
      setStreamText('')
    }
  }

  const canSend = !!chatId && !!text.trim() && !busy

  return (
    <div className={styles.main}>
      <Card className={styles.card}>
        <div className={styles.history}>
          {messages.map(m => (
            <div key={m.id} className={m.role === 'user' ? styles.userMsg : styles.assistantMsg}>
              <div className={styles.body}>{m.content}</div>
            </div>
          ))}
          {streamText && (
            <div className={styles.assistantMsg}>
              <div className={styles.body}>{streamText}</div>
            </div>
          )}
          {messages.length === 0 && !state.isLoading && (
            <div style={{ opacity: .7 }}>Сообщений пока нет.</div>
          )}
        </div>

        <div className={styles.composer}>
          <Textarea
            placeholder="Ваше сообщение…"
            value={text}
            onChange={e => setText(e.target.value)}
            disabled={!chatId || busy}
            rows={3}
          />
          <div className={styles.controls}>
            <div />
            <div className={styles.actionsBottom}>
              <Button onClick={onSend} disabled={!canSend}>Отправить</Button>
              <label className={styles.ragToggle} title="Использовать базу знаний (RAG) при ответе">
                <input type="checkbox" checked={useRag} onChange={e => setUseRag(e.target.checked)} />
                RAG из БЗ
              </label>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

import React, { useEffect, useRef, useState } from 'react'
import styles from './Chat.module.css'
import Card from '@shared/ui/Card'
import Button from '@shared/ui/Button'
import Textarea from '@shared/ui/Textarea'
import * as chats from '@shared/api/chats'
import { useNavigate, useParams } from 'react-router-dom'

type Msg = { role: 'user' | 'assistant'; content: string }

export default function Chat() {
  const { chatId } = useParams()
  const nav = useNavigate()
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [items, setItems] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [useRag, setUseRag] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    (async () => {
      if (!chatId) {
        const { chat_id } = await chats.createChat()
        nav(`/gpt/chat/${chat_id}`, { replace: true })
        return
      }
      setCurrentId(chatId)
    })()
  }, [chatId])

  useEffect(() => {
    (async () => {
      if (!currentId) return
      try {
        const res = await chats.listMessages(currentId, { limit: 100 })
        const msgs = (res.items || []) as Msg[]
        setItems(msgs)
      } catch { setItems([]) }
    })()
  }, [currentId])

  useEffect(() => {
    boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight, behavior: 'smooth' })
  }, [items.length])

  async function onSend() {
    const content = text.trim()
    if (!content || !currentId) return
    setBusy(true)
    setItems(prev => [...prev, { role: 'user', content }])
    setText('')
    try {
      const res = await chats.chat(currentId, { content, use_rag: useRag })
      setItems(prev => [...prev, { role: 'assistant', content: res.answer || '' }])
    } finally { setBusy(false) }
    taRef.current?.focus()
  }

  return (
    <div className={styles.wrap}>
      <Card className={styles.panel} ref={boxRef as any}>
        <div className={styles.messages}>
          {items.length === 0 && <div className={styles.empty}>Пока нет сообщений</div>}
          {items.map((m, i) => (
            <div key={i} className={m.role === 'user' ? styles.user : styles.assistant}>{m.content}</div>
          ))}
          {busy && <div className={[styles.assistant, styles.typing].join(' ')}>…</div>}
        </div>
        <div className={styles.composer}>
          <div className={styles.inputArea}>
            <Textarea
              ref={taRef}
              placeholder="Спросите что-нибудь… (Enter — новая строка)"
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

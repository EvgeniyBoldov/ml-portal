import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
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
  const [useRag, setUseRag] = useState(false)   // default: unchecked
  const boxRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)
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

  const resizeTA = () => {
    const panel = panelRef.current
    const composer = composerRef.current
    const ta = taRef.current
    if (!panel || !composer || !ta) return
    const maxComposer = Math.floor(panel.clientHeight * 0.30)
    composer.style.minHeight = '120px'
    composer.style.maxHeight = maxComposer + 'px'
    ta.style.height = 'auto'
    const newH = Math.min(ta.scrollHeight, Math.max(80, maxComposer - 24))
    ta.style.height = newH + 'px'
  }
  useLayoutEffect(() => { resizeTA() }, [])
  useEffect(() => { resizeTA() }, [text])
  useEffect(() => {
    const onResize = () => resizeTA()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  async function onSend() {
    const id = currentId
    if (!id || !text.trim()) return
    const question = text.trim()
    setText('')
    setItems(prev => [...prev, { role: 'user', content: question }, { role: 'assistant', content: '' }])
    setBusy(true)
    try {
      let acc = ''
      for await (const chunk of chats.sendMessageStream(id, {
        messages: [{ role:'user', content: question }],
        use_rag: useRag
      })) {
        acc += chunk
        setItems(prev => {
          const next = [...prev]
          next[next.length-1] = { role: 'assistant', content: acc }
          return next
        })
      }
    } catch (e:any) {
      setItems(prev => [...prev, { role:'assistant', content: '⚠️ ' + (e.message||'Error') }])
    } finally {
      setBusy(false)
      setUseRag(false)  // auto-uncheck after sending
      resizeTA()
    }
  }

  return (
    <div className={styles.wrap}>
      <Card className={styles.panel} ref={panelRef}>
        <div className={styles.messages} ref={boxRef}>
          {items.length === 0 && <div className={styles.empty}>Начните диалог…</div>}
          {items.map((m, i) => (
            <div key={i} className={m.role === 'user' ? styles.user : styles.assistant}>
              {m.content || <span className={styles.typing}>печатает…</span>}
            </div>
          ))}
        </div>

        <div className={styles.composer} ref={composerRef}>
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
              <Button onClick={onSend} disabled={busy || !text.trim()}>Send</Button>
              <label className={styles.ragToggle} title="Использовать базу знаний (RAG) при ответе">
                <input type="checkbox" checked={useRag} onChange={e=>setUseRag(e.target.checked)} />
                Use RAG
              </label>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

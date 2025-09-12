import React, { useState } from 'react'
import { useChat } from '../contexts/ChatContext'
import Button from '@shared/ui/Button'
import Modal from '@shared/ui/Modal'
import styles from './ChatExport.module.css'

export default function ChatExport() {
  const { state } = useChat()
  const [isOpen, setIsOpen] = useState(false)
  const [exportFormat, setExportFormat] = useState<'json' | 'txt' | 'md'>('json')

  const exportChats = () => {
    const chats = state.chatsOrder.map(id => state.chatsById[id])
    
    if (exportFormat === 'json') {
      const data = chats.map(chat => ({
        id: chat.id,
        name: chat.name,
        created_at: chat.created_at,
        messages: (state.messagesByChat[chat.id]?.items || []).map(msg => ({
          role: msg.role,
          content: msg.content,
          created_at: msg.created_at
        }))
      }))
      
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chats_export_${new Date().toISOString().split('T')[0]}.json`
      a.click()
      URL.revokeObjectURL(url)
    } else if (exportFormat === 'txt') {
      const content = chats.map(chat => {
        let text = `=== ${chat.name || 'Untitled'} ===\n`
        text += `Created: ${chat.created_at ? new Date(chat.created_at).toLocaleString() : 'Unknown'}\n\n`
        
        const messages = state.messagesByChat[chat.id]?.items || []
        messages.forEach(msg => {
          text += `${msg.role.toUpperCase()}: ${msg.content}\n\n`
        })
        
        return text
      }).join('\n' + '='.repeat(50) + '\n\n')
      
      const blob = new Blob([content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chats_export_${new Date().toISOString().split('T')[0]}.txt`
      a.click()
      URL.revokeObjectURL(url)
    } else if (exportFormat === 'md') {
      const content = chats.map(chat => {
        let md = `# ${chat.name || 'Untitled'}\n\n`
        md += `**Created:** ${chat.created_at ? new Date(chat.created_at).toLocaleString() : 'Unknown'}\n\n`
        
        const messages = state.messagesByChat[chat.id]?.items || []
        messages.forEach(msg => {
          md += `## ${msg.role === 'user' ? '👤 User' : '🤖 Assistant'}\n\n`
          md += `${msg.content}\n\n`
        })
        
        return md
      }).join('\n---\n\n')
      
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chats_export_${new Date().toISOString().split('T')[0]}.md`
      a.click()
      URL.revokeObjectURL(url)
    }
    
    setIsOpen(false)
  }

  return (
    <>
      <Button 
        onClick={() => setIsOpen(true)}
        size="small"
        variant="ghost"
        title="Экспорт чатов"
      >
        📤
      </Button>

      <Modal 
        open={isOpen} 
        onClose={() => setIsOpen(false)} 
        title="Экспорт чатов"
        footer={
          <>
            <Button variant="ghost" onClick={() => setIsOpen(false)}>
              Отмена
            </Button>
            <Button onClick={exportChats}>
              Экспортировать
            </Button>
          </>
        }
      >
        <div className={styles.exportOptions}>
          <p>Выберите формат экспорта:</p>
          
          <div className={styles.formatOptions}>
            <label className={styles.formatOption}>
              <input
                type="radio"
                name="format"
                value="json"
                checked={exportFormat === 'json'}
                onChange={e => setExportFormat(e.target.value as 'json')}
              />
              <span>JSON (полные данные)</span>
            </label>
            
            <label className={styles.formatOption}>
              <input
                type="radio"
                name="format"
                value="txt"
                checked={exportFormat === 'txt'}
                onChange={e => setExportFormat(e.target.value as 'txt')}
              />
              <span>TXT (текстовый формат)</span>
            </label>
            
            <label className={styles.formatOption}>
              <input
                type="radio"
                name="format"
                value="md"
                checked={exportFormat === 'md'}
                onChange={e => setExportFormat(e.target.value as 'md')}
              />
              <span>Markdown (для документации)</span>
            </label>
          </div>
          
          <div className={styles.exportInfo}>
            <p>Будет экспортировано чатов: <strong>{state.chatsOrder.length}</strong></p>
            <p>Общее количество сообщений: <strong>
              {state.chatsOrder.reduce((sum, chatId) => sum + (state.messagesByChat[chatId]?.items.length || 0), 0)}
            </strong></p>
          </div>
        </div>
      </Modal>
    </>
  )
}

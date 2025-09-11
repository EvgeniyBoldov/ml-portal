import React, { useState } from 'react'
import { useChat } from '../contexts/ChatContext'
import Button from '@shared/ui/Button'
import Input from '@shared/ui/Input'
import Modal from '@shared/ui/Modal'
import styles from './ChatTags.module.css'

interface ChatTagsProps {
  chatId: string
  tags: string[]
  onTagsChange?: (tags: string[]) => void
}

export default function ChatTags({ chatId, tags, onTagsChange }: ChatTagsProps) {
  const { updateChatTags } = useChat()
  const [isOpen, setIsOpen] = useState(false)
  const [newTag, setNewTag] = useState('')
  const [currentTags, setCurrentTags] = useState<string[]>(tags)

  const handleAddTag = () => {
    if (newTag.trim() && !currentTags.includes(newTag.trim())) {
      const updatedTags = [...currentTags, newTag.trim()]
      setCurrentTags(updatedTags)
      setNewTag('')
    }
  }

  const handleRemoveTag = (tagToRemove: string) => {
    const updatedTags = currentTags.filter(tag => tag !== tagToRemove)
    setCurrentTags(updatedTags)
  }

  const handleSave = async () => {
    try {
      await updateChatTags(chatId, currentTags)
      onTagsChange?.(currentTags)
      setIsOpen(false)
    } catch (error) {
      console.error('Failed to update tags:', error)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddTag()
    }
  }

  return (
    <>
      <div className={styles.tagsContainer}>
        {currentTags.length > 0 ? (
          <div className={styles.tagsList}>
            {currentTags.map(tag => (
              <span key={tag} className={styles.tag}>
                {tag}
                <button
                  className={styles.removeTag}
                  onClick={() => handleRemoveTag(tag)}
                  title="Удалить тег"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : (
          <span className={styles.noTags}>Нет тегов</span>
        )}
        <Button
          size="small"
          variant="ghost"
          onClick={() => setIsOpen(true)}
          title="Управление тегами"
        >
          {currentTags.length > 0 ? '✏️' : '🏷️'}
        </Button>
      </div>

      <Modal
        open={isOpen}
        onClose={() => setIsOpen(false)}
        title="Управление тегами"
        footer={
          <>
            <Button variant="ghost" onClick={() => setIsOpen(false)}>
              Отмена
            </Button>
            <Button onClick={handleSave}>
              Сохранить
            </Button>
          </>
        }
      >
        <div className={styles.tagEditor}>
          <div className={styles.addTagForm}>
            <Input
              value={newTag}
              onChange={e => setNewTag(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Добавить тег..."
            />
            <Button onClick={handleAddTag} disabled={!newTag.trim()}>
              Добавить
            </Button>
          </div>
          
          <div className={styles.tagsList}>
            {currentTags.map(tag => (
              <div key={tag} className={styles.tagItem}>
                <span className={styles.tagName}>{tag}</span>
                <button
                  className={styles.removeButton}
                  onClick={() => handleRemoveTag(tag)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          
          {currentTags.length === 0 && (
            <div className={styles.emptyState}>
              <p>Теги помогают организовать чаты по темам</p>
              <p>Например: "работа", "личное", "проект-альфа"</p>
            </div>
          )}
        </div>
      </Modal>
    </>
  )
}

import React, { useState, useEffect } from 'react'
import Card from '@shared/ui/Card'
import Button from '@shared/ui/Button'
import FilePicker from '@shared/ui/FilePicker'
import Input from '@shared/ui/Input'
import * as rag from '@shared/api/rag'
import { RagDocument } from '@shared/api/types'
import ChatTags from '../../components/ChatTags'
import styles from './RagPage.module.css'

export default function Rag() {
  const [documents, setDocuments] = useState<RagDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadTags, setUploadTags] = useState<string[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const [pagination, setPagination] = useState({
    page: 1,
    size: 20,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_prev: false
  })
  const [filters, setFilters] = useState({
    status: '',
    search: ''
  })
  const [metrics, setMetrics] = useState<any>(null)

  useEffect(() => {
    loadDocuments()
    loadMetrics()
  }, [])

  const loadDocuments = async (page = 1) => {
    setLoading(true)
    try {
      const res = await rag.listDocs({
        page,
        size: pagination.size,
        status: filters.status || undefined,
        search: filters.search || undefined
      })
      setDocuments(res.items || [])
      setPagination(res.pagination || pagination)
    } catch (error) {
      console.error('Failed to load documents:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadMetrics = async () => {
    try {
      const res = await rag.getRagMetrics()
      setMetrics(res)
    } catch (error) {
      console.error('Failed to load metrics:', error)
    }
  }

  const handleFileUpload = async (file: File) => {
    setUploading(true)
    try {
      await rag.uploadFile(file, file.name, uploadTags)
      setUploadTags([]) // Сбрасываем теги после загрузки
      await loadDocuments()
      await loadMetrics()
    } catch (error) {
      console.error('Failed to upload file:', error)
      alert('Ошибка загрузки файла')
    } finally {
      setUploading(false)
    }
  }

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }))
    setPagination(prev => ({ ...prev, page: 1 }))
  }

  const handlePageChange = (page: number) => {
    loadDocuments(page)
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const res = await rag.ragSearch({ text: searchQuery, top_k: 10 })
      setSearchResults(res.items || [])
    } catch (error) {
      console.error('Search failed:', error)
    } finally {
      setSearching(false)
    }
  }

  const handleFilterApply = () => {
    loadDocuments(1)
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
      await loadDocuments()
    } catch (error) {
      console.error('Archive failed:', error)
    }
  }

  const handleDelete = async (doc: RagDocument) => {
    if (!confirm('Удалить документ?')) return
    try {
      await rag.deleteRagDocument(doc.id)
      await loadDocuments()
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

  const handleUpdateTags = async (docId: string, tags: string[]) => {
    try {
      await rag.updateRagDocumentTags(docId, tags)
      await loadDocuments() // Перезагружаем список документов
    } catch (error) {
      console.error('Failed to update tags:', error)
      alert('Ошибка обновления тегов')
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ready': return '#4caf50'
      case 'processing': return '#ff9800'
      case 'error': return '#f44336'
      case 'archived': return '#9e9e9e'
      default: return '#2196f3'
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

  return (
    <div className={styles.container}>
      <Card className={styles.uploadCard}>
        <h3>Загрузка документа</h3>
        <FilePicker
          onFileSelected={(file) => file && handleFileUpload(file)}
          accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt"
          disabled={uploading}
        />
        <div className={styles.uploadTags}>
          <label>Теги (опционально):</label>
          <ChatTags 
            chatId="upload" 
            tags={uploadTags} 
            onTagsChange={setUploadTags}
          />
        </div>
        {uploading && <p>Загрузка...</p>}
      </Card>

      <Card className={styles.searchCard}>
        <h3>Поиск по базе знаний</h3>
        <div className={styles.searchForm}>
          <Input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Введите запрос для поиска..."
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <Button onClick={handleSearch} disabled={searching || !searchQuery.trim()}>
            {searching ? 'Поиск...' : 'Найти'}
          </Button>
        </div>
        
        {searchResults.length > 0 && (
          <div className={styles.searchResults}>
            <h4>Результаты поиска:</h4>
            {searchResults.map((item, i) => (
              <div key={i} className={styles.searchItem}>
                <div className={styles.searchScore}>{(item.score * 100).toFixed(1)}%</div>
                <div className={styles.searchSnippet}>{item.snippet}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className={styles.documentsCard}>
        <div className={styles.documentsHeader}>
          <h3>Документы ({pagination.total})</h3>
          {metrics && (
            <div className={styles.metrics}>
              <span>Готово: {metrics.ready_documents}</span>
              <span>Ошибки: {metrics.error_documents}</span>
              <span>Размер: {metrics.storage_size_mb} MB</span>
            </div>
          )}
        </div>
        
        <div className={styles.filters}>
          <Input
            value={filters.search}
            onChange={e => handleFilterChange('search', e.target.value)}
            placeholder="Поиск по названию..."
            onKeyDown={e => e.key === 'Enter' && handleFilterApply()}
          />
          <select
            value={filters.status}
            onChange={e => handleFilterChange('status', e.target.value)}
            className={styles.statusFilter}
          >
            <option value="">Все статусы</option>
            <option value="uploaded">Загружено</option>
            <option value="processing">Обработка</option>
            <option value="ready">Готово</option>
            <option value="error">Ошибка</option>
            <option value="archived">Архив</option>
          </select>
          <Button onClick={handleFilterApply}>Применить</Button>
        </div>

        {loading ? (
          <p>Загрузка...</p>
        ) : documents.length === 0 ? (
          <p>Нет документов</p>
        ) : (
          <div className={styles.documentsList}>
            {documents.map(doc => (
              <div key={doc.id} className={styles.documentItem}>
                <div className={styles.documentInfo}>
                  <div className={styles.documentName}>
                    {doc.name || `Документ ${doc.id.slice(0, 8)}`}
                  </div>
                  <div className={styles.documentStatus}>
                    <span 
                      className={styles.statusBadge}
                      style={{ backgroundColor: getStatusColor(doc.status) }}
                    >
                      {getStatusText(doc.status)}
                    </span>
                    {doc.progress !== undefined && doc.status === 'processing' && (
                      <span className={styles.progress}>
                        {Math.round(doc.progress * 100)}%
                      </span>
                    )}
                  </div>
                  <div className={styles.documentDate}>
                    {doc.date_upload && new Date(doc.date_upload).toLocaleString()}
                  </div>
                  <div className={styles.documentTags}>
                    <ChatTags 
                      chatId={doc.id} 
                      tags={doc.tags || []} 
                      onTagsChange={(tags) => handleUpdateTags(doc.id, tags)}
                    />
                  </div>
                </div>
                <div className={styles.documentActions}>
                  {doc.status === 'ready' && (
                    <>
                      <Button 
                        size="small" 
                        onClick={() => handleDownload(doc, 'original')}
                      >
                        Скачать
                      </Button>
                      {doc.url_canonical_file && (
                        <Button 
                          size="small" 
                          onClick={() => handleDownload(doc, 'canonical')}
                        >
                          Каноническая форма
                        </Button>
                      )}
                      <Button 
                        size="small" 
                        onClick={() => handleReindex(doc)}
                        title="Переиндексировать документ"
                      >
                        🔄
                      </Button>
                    </>
                  )}
                  {doc.status === 'ready' && (
                    <Button 
                      size="small" 
                      onClick={() => handleArchive(doc)}
                    >
                      Архивировать
                    </Button>
                  )}
                  <Button 
                    size="small" 
                    variant="danger"
                    onClick={() => handleDelete(doc)}
                  >
                    Удалить
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {pagination.total_pages > 1 && (
          <div className={styles.pagination}>
            <Button 
              onClick={() => handlePageChange(pagination.page - 1)}
              disabled={!pagination.has_prev}
            >
              ←
            </Button>
            <span className={styles.pageInfo}>
              Страница {pagination.page} из {pagination.total_pages}
            </span>
            <Button 
              onClick={() => handlePageChange(pagination.page + 1)}
              disabled={!pagination.has_next}
            >
              →
            </Button>
          </div>
        )}
    </Card>
    </div>
  )
}

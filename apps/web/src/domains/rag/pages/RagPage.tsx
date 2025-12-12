import React, { useState, useCallback, useMemo, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import Modal from '@shared/ui/Modal';
import { Icon } from '@shared/ui/Icon';
import { useToast } from '@shared/ui/Toast';
import { useRBAC } from '@shared/hooks/useRBAC';
import {
  useRagDocuments,
  useUploadRagDocument,
  useDeleteRagDocument,
  useUpdateRagTags,
  useUpdateRagScope,
} from '@shared/api/hooks/useRagDocuments';
import {
  startRagIngest,
  cancelRagDocument,
} from '@shared/api/rag';
import type { RagDocument } from '@shared/api/types/rag';
import { StatusModalNew } from '../components/StatusModalNew';
import styles from './RagPage.module.css';

type StatusFilter = 'all' | 'ready' | 'processing' | 'failed' | 'uploaded';
type ScopeFilter = 'all' | 'local' | 'global';
type SortKey = 'name' | 'created_at' | 'agg_status';
type SortDir = 'asc' | 'desc';

interface StatCard {
  label: string;
  value: number;
  color: 'primary' | 'success' | 'warning' | 'danger' | 'neutral';
  filter: StatusFilter;
}

export default function RagPage() {
  const queryClient = useQueryClient();
  const { isAdmin } = useRBAC();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filters & sorting
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Selection for bulk actions
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Modals
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [statusModalDocId, setStatusModalDocId] = useState<string | null>(null);
  const [tagsModalDoc, setTagsModalDoc] = useState<RagDocument | null>(null);
  const [tagsInput, setTagsInput] = useState('');

  // Upload state
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadTags, setUploadTags] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  // Data
  const { data, isLoading } = useRagDocuments({ page: 1, size: 500 });
  const uploadMutation = useUploadRagDocument();
  const deleteMutation = useDeleteRagDocument();
  const updateTagsMutation = useUpdateRagTags();
  const updateScopeMutation = useUpdateRagScope();

  const documents = data?.items || [];

  // Stats calculation
  const stats = useMemo(() => {
    const counts = {
      total: documents.length,
      ready: 0,
      processing: 0,
      failed: 0,
      uploaded: 0,
    };

    documents.forEach(doc => {
      const status = doc.agg_status || 'uploaded';
      if (status === 'ready') counts.ready++;
      else if (['processing', 'embedding', 'chunked', 'normalized'].includes(status)) counts.processing++;
      else if (status === 'failed') counts.failed++;
      else counts.uploaded++;
    });

    return counts;
  }, [documents]);

  const statCards: StatCard[] = [
    { label: 'Всего', value: stats.total, color: 'neutral', filter: 'all' },
    { label: 'Готово', value: stats.ready, color: 'success', filter: 'ready' },
    { label: 'В обработке', value: stats.processing, color: 'warning', filter: 'processing' },
    { label: 'Ошибки', value: stats.failed, color: 'danger', filter: 'failed' },
  ];

  // Filtering & sorting
  const filteredDocuments = useMemo(() => {
    let result = [...documents];

    // Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(doc =>
        (doc.name || '').toLowerCase().includes(q) ||
        (doc.tags?.join(' ') || '').toLowerCase().includes(q)
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(doc => {
        const status = doc.agg_status || 'uploaded';
        if (statusFilter === 'ready') return status === 'ready';
        if (statusFilter === 'processing') return ['processing', 'embedding', 'chunked', 'normalized'].includes(status);
        if (statusFilter === 'failed') return status === 'failed';
        if (statusFilter === 'uploaded') return status === 'uploaded';
        return true;
      });
    }

    // Scope filter
    if (scopeFilter !== 'all') {
      result = result.filter(doc => doc.scope === scopeFilter);
    }

    // Sorting
    result.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'name') {
        cmp = (a.name || '').localeCompare(b.name || '');
      } else if (sortKey === 'created_at') {
        cmp = (a.created_at || '').localeCompare(b.created_at || '');
      } else if (sortKey === 'agg_status') {
        cmp = (a.agg_status || '').localeCompare(b.agg_status || '');
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [documents, searchQuery, statusFilter, scopeFilter, sortKey, sortDir]);

  // Handlers
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const handleSelectAll = () => {
    if (selectedIds.size === filteredDocuments.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredDocuments.map(d => d.id)));
    }
  };

  const handleSelect = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedIds(newSet);
  };

  // Drag & Drop
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      setUploadFiles(files);
      setUploadModalOpen(true);
    }
  }, []);

  // Upload
  const handleUpload = async () => {
    if (uploadFiles.length === 0) return;

    const tags = uploadTags.split(',').map(t => t.trim()).filter(Boolean);

    try {
      const results = await Promise.allSettled(
        uploadFiles.map(file =>
          uploadMutation.mutateAsync({ file, filename: file.name, tags })
        )
      );

      const succeeded = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;

      if (succeeded > 0) {
        showToast(`Загружено: ${succeeded} файлов`, 'success');
      }
      if (failed > 0) {
        showToast(`Ошибка загрузки: ${failed} файлов`, 'error');
      }

      setUploadModalOpen(false);
      setUploadFiles([]);
      setUploadTags('');
    } catch (error) {
      showToast('Ошибка загрузки', 'error');
    }
  };

  // Bulk actions
  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Удалить ${selectedIds.size} документов?`)) return;

    try {
      await Promise.all(
        Array.from(selectedIds).map(id => deleteMutation.mutateAsync(id))
      );
      showToast(`Удалено: ${selectedIds.size} документов`, 'success');
      setSelectedIds(new Set());
    } catch (error) {
      showToast('Ошибка удаления', 'error');
    }
  };

  const handleBulkIngest = async () => {
    if (selectedIds.size === 0) return;

    try {
      await Promise.all(
        Array.from(selectedIds).map(id => startRagIngest(id))
      );
      // Invalidate list to update statuses
      queryClient.invalidateQueries({ queryKey: ['rag', 'list'] });
      showToast(`Ингест запущен: ${selectedIds.size} документов`, 'success');
      setSelectedIds(new Set());
    } catch (error) {
      showToast('Ошибка запуска ингеста', 'error');
    }
  };

  // Single document actions
  const handleDelete = async (doc: RagDocument) => {
    if (!confirm(`Удалить "${doc.name}"?`)) return;
    try {
      await deleteMutation.mutateAsync(doc.id);
      showToast('Документ удален', 'success');
    } catch (error) {
      showToast('Ошибка удаления', 'error');
    }
  };

  const handleIngest = async (doc: RagDocument) => {
    try {
      await startRagIngest(doc.id);
      // Invalidate list to update status
      queryClient.invalidateQueries({ queryKey: ['rag', 'list'] });
      queryClient.invalidateQueries({ queryKey: ['rag', 'detail', doc.id] });
      showToast('Ингест запущен', 'success');
    } catch (error) {
      showToast('Ошибка запуска ингеста', 'error');
    }
  };

  const handleCancel = async (doc: RagDocument) => {
    try {
      await cancelRagDocument(doc.id);
      showToast('Обработка отменена', 'success');
    } catch (error) {
      showToast('Ошибка отмены', 'error');
    }
  };

  const handleToggleScope = async (doc: RagDocument) => {
    const newScope = doc.scope === 'local' ? 'global' : 'local';
    if (newScope === 'global' && !confirm('Сделать документ глобальным? Это действие необратимо.')) {
      return;
    }
    try {
      await updateScopeMutation.mutateAsync({ docId: doc.id, scope: newScope });
      showToast(`Скоуп изменен на ${newScope === 'local' ? 'локальный' : 'глобальный'}`, 'success');
    } catch (error) {
      showToast('Ошибка изменения скоупа', 'error');
    }
  };

  const handleSaveTags = async () => {
    if (!tagsModalDoc) return;
    const tags = tagsInput.split(',').map(t => t.trim()).filter(Boolean);
    try {
      await updateTagsMutation.mutateAsync({ docId: tagsModalDoc.id, tags });
      showToast('Теги обновлены', 'success');
      setTagsModalDoc(null);
    } catch (error) {
      showToast('Ошибка обновления тегов', 'error');
    }
  };

  const openTagsModal = (doc: RagDocument) => {
    setTagsModalDoc(doc);
    setTagsInput((doc.tags || []).join(', '));
  };

  // Status helpers
  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { tone: 'success' | 'warning' | 'danger' | 'info' | 'neutral'; label: string }> = {
      ready: { tone: 'success', label: 'Готов' },
      processing: { tone: 'warning', label: 'Обработка' },
      embedding: { tone: 'warning', label: 'Эмбеддинг' },
      chunked: { tone: 'info', label: 'Разбит' },
      normalized: { tone: 'info', label: 'Нормализован' },
      failed: { tone: 'danger', label: 'Ошибка' },
      uploaded: { tone: 'neutral', label: 'Загружен' },
    };
    const config = statusMap[status] || { tone: 'neutral' as const, label: status };
    const isProcessing = ['processing', 'embedding', 'chunked', 'normalized'].includes(status);
    
    return (
      <Badge tone={config.tone} className={isProcessing ? styles.pulsing : ''}>
        {config.label}
      </Badge>
    );
  };

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '—';
    }
  };

  return (
    <div
      className={`${styles.page} ${isDragging ? styles.dragging : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drop overlay */}
      {isDragging && (
        <div className={styles.dropOverlay}>
          <div className={styles.dropContent}>
            <Icon name="upload" size={48} />
            <span>Перетащите файлы для загрузки</span>
          </div>
        </div>
      )}

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>База знаний</h1>
          <span className={styles.subtitle}>
            Управление документами и индексацией
          </span>
        </div>
        <div className={styles.headerRight}>
          <Button variant="primary" onClick={() => setUploadModalOpen(true)}>
            <Icon name="upload" size={16} />
            Загрузить
          </Button>
        </div>
      </header>

      {/* Stats */}
      <div className={styles.stats}>
        {statCards.map(card => (
          <button
            key={card.label}
            className={`${styles.statCard} ${styles[card.color]} ${statusFilter === card.filter ? styles.active : ''}`}
            onClick={() => setStatusFilter(card.filter)}
          >
            <span className={styles.statValue}>{card.value}</span>
            <span className={styles.statLabel}>{card.label}</span>
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <Input
            className={styles.search}
            placeholder="Поиск по имени или тегам..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          <select
            className={styles.select}
            value={scopeFilter}
            onChange={e => setScopeFilter(e.target.value as ScopeFilter)}
          >
            <option value="all">Все скоупы</option>
            <option value="local">Локальные</option>
            <option value="global">Глобальные</option>
          </select>
        </div>
        <div className={styles.toolbarRight}>
          {selectedIds.size > 0 && (
            <div className={styles.bulkActions}>
              <span className={styles.selectedCount}>
                Выбрано: {selectedIds.size}
              </span>
              <Button variant="ghost" size="sm" onClick={handleBulkIngest}>
                Запустить ингест
              </Button>
              <Button variant="danger" size="sm" onClick={handleBulkDelete}>
                Удалить
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                Отменить
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className={styles.tableContainer}>
        {isLoading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <span>Загрузка документов...</span>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className={styles.empty}>
            <Icon name="file-text" size={48} className={styles.emptyIcon} />
            <h3>Документы не найдены</h3>
            <p>
              {searchQuery || statusFilter !== 'all' || scopeFilter !== 'all'
                ? 'Попробуйте изменить фильтры'
                : 'Загрузите первый документ для начала работы'}
            </p>
            {!searchQuery && statusFilter === 'all' && scopeFilter === 'all' && (
              <Button onClick={() => setUploadModalOpen(true)}>
                Загрузить документ
              </Button>
            )}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.checkboxCell}>
                  <input
                    type="checkbox"
                    checked={selectedIds.size === filteredDocuments.length && filteredDocuments.length > 0}
                    onChange={handleSelectAll}
                  />
                </th>
                <th className={styles.sortable} onClick={() => handleSort('name')}>
                  Название
                  {sortKey === 'name' && (
                    <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />
                  )}
                </th>
                <th className={styles.sortable} onClick={() => handleSort('agg_status')}>
                  Статус
                  {sortKey === 'agg_status' && (
                    <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />
                  )}
                </th>
                <th>Скоуп</th>
                <th>Теги</th>
                <th className={styles.sortable} onClick={() => handleSort('created_at')}>
                  Создан
                  {sortKey === 'created_at' && (
                    <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />
                  )}
                </th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map(doc => {
                const isProcessing = ['processing', 'embedding', 'chunked', 'normalized'].includes(doc.agg_status || '');
                return (
                  <tr key={doc.id} className={selectedIds.has(doc.id) ? styles.selected : ''}>
                    <td className={styles.checkboxCell}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(doc.id)}
                        onChange={() => handleSelect(doc.id)}
                      />
                    </td>
                    <td className={styles.nameCell}>
                      <button
                        className={styles.nameButton}
                        onClick={() => setStatusModalDocId(doc.id)}
                      >
                        {doc.name || 'Без имени'}
                      </button>
                    </td>
                    <td>
                      <button
                        className={styles.statusButton}
                        onClick={() => setStatusModalDocId(doc.id)}
                      >
                        {getStatusBadge(doc.agg_status || 'uploaded')}
                      </button>
                    </td>
                    <td>
                      <Badge tone={doc.scope === 'global' ? 'success' : 'neutral'}>
                        {doc.scope === 'global' ? 'Глобальный' : 'Локальный'}
                      </Badge>
                    </td>
                    <td className={styles.tagsCell}>
                      {doc.tags && doc.tags.length > 0 ? (
                        <div className={styles.tags}>
                          {doc.tags.slice(0, 3).map(tag => (
                            <span key={tag} className={styles.tag}>{tag}</span>
                          ))}
                          {doc.tags.length > 3 && (
                            <span className={styles.tagMore}>+{doc.tags.length - 3}</span>
                          )}
                        </div>
                      ) : (
                        <span className={styles.muted}>—</span>
                      )}
                    </td>
                    <td className={styles.muted}>
                      {formatDate(doc.created_at)}
                    </td>
                    <td>
                      <div className={styles.actions}>
                        {isProcessing ? (
                          <button
                            className={styles.actionBtn}
                            onClick={() => handleCancel(doc)}
                            title="Отменить обработку"
                          >
                            <Icon name="x" size={16} />
                          </button>
                        ) : doc.agg_status !== 'ready' ? (
                          <button
                            className={styles.actionBtn}
                            onClick={() => handleIngest(doc)}
                            title="Запустить ингест"
                          >
                            <Icon name="play" size={16} />
                          </button>
                        ) : null}
                        <button
                          className={styles.actionBtn}
                          onClick={() => openTagsModal(doc)}
                          title="Редактировать теги"
                        >
                          <Icon name="tag" size={16} />
                        </button>
                        {doc.scope === 'local' && (
                          <button
                            className={styles.actionBtn}
                            onClick={() => handleToggleScope(doc)}
                            title="Сделать глобальным"
                          >
                            <Icon name="globe" size={16} />
                          </button>
                        )}
                        <button
                          className={`${styles.actionBtn} ${styles.danger}`}
                          onClick={() => handleDelete(doc)}
                          title="Удалить"
                        >
                          <Icon name="trash" size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Upload Modal */}
      <Modal
        open={uploadModalOpen}
        onClose={() => {
          setUploadModalOpen(false);
          setUploadFiles([]);
          setUploadTags('');
        }}
        title="Загрузка документов"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadModalOpen(false)}>
              Отмена
            </Button>
            <Button
              onClick={handleUpload}
              disabled={uploadFiles.length === 0 || uploadMutation.isLoading}
            >
              {uploadMutation.isLoading ? 'Загрузка...' : `Загрузить (${uploadFiles.length})`}
            </Button>
          </>
        }
      >
        <div className={styles.uploadContent}>
          <div
            className={styles.dropZone}
            onClick={() => fileInputRef.current?.click()}
          >
            <Icon name="upload" size={32} />
            <span>Нажмите или перетащите файлы</span>
            <span className={styles.dropZoneHint}>
              Поддерживаются: PDF, DOC, DOCX, TXT, MD
            </span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt"
            style={{ display: 'none' }}
            onChange={e => {
              const files = Array.from(e.target.files || []);
              setUploadFiles(prev => [...prev, ...files]);
            }}
          />

          {uploadFiles.length > 0 && (
            <div className={styles.fileList}>
              {uploadFiles.map((file, idx) => (
                <div key={`${file.name}-${idx}`} className={styles.fileItem}>
                  <Icon name="file-text" size={16} />
                  <span className={styles.fileName}>{file.name}</span>
                  <span className={styles.fileSize}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </span>
                  <button
                    className={styles.fileRemove}
                    onClick={() => setUploadFiles(files => files.filter((_, i) => i !== idx))}
                  >
                    <Icon name="x" size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className={styles.formGroup}>
            <label>Теги (через запятую)</label>
            <Input
              placeholder="документация, api, важное..."
              value={uploadTags}
              onChange={e => setUploadTags(e.target.value)}
            />
          </div>
        </div>
      </Modal>

      {/* Tags Modal */}
      <Modal
        open={!!tagsModalDoc}
        onClose={() => setTagsModalDoc(null)}
        title={`Теги: ${tagsModalDoc?.name || ''}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTagsModalDoc(null)}>
              Отмена
            </Button>
            <Button onClick={handleSaveTags} disabled={updateTagsMutation.isLoading}>
              {updateTagsMutation.isLoading ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </>
        }
      >
        <div className={styles.formGroup}>
          <label>Введите теги через запятую</label>
          <Input
            placeholder="документация, api, важное..."
            value={tagsInput}
            onChange={e => setTagsInput(e.target.value)}
          />
        </div>
      </Modal>

      {/* Status Modal */}
      {statusModalDocId && (
        <StatusModalNew
          docId={statusModalDocId}
          docName={documents.find((d: RagDocument) => d.id === statusModalDocId)?.name}
          onClose={() => setStatusModalDocId(null)}
        />
      )}
    </div>
  );
}

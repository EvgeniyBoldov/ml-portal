import React, { useState, useCallback, useMemo } from 'react';
import Card from '@shared/ui/Card';
import Input from '@shared/ui/Input';
import Button from '@shared/ui/Button';
import Badge from '@shared/ui/Badge';
import Popover from '@shared/ui/Popover';
import { useToast } from '@shared/ui/Toast';
import { useRBAC } from '@shared/hooks/useRBAC';

// Импорты компонентов
import { DocumentList, Uploader } from '@/domains/rag/components';

// Импорты API
import {
  startRagIngest,
  updateRagDocumentTags,
  updateRagDocumentScope,
} from '@shared/api/rag';
import {
  useRagDocuments,
  useUploadRagDocument,
  useDeleteRagDocument,
} from '@shared/api/hooks/useRagDocuments';
import type { RagDocument } from '@shared/api/types/rag';

import styles from './Rag.module.css';

type ColKey = 'name' | 'status' | 'created_at' | 'tags';

export default function Rag() {
  const { isAdmin } = useRBAC();

  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState<Partial<Record<ColKey, string>>>({});

  // Состояние загрузки
  const [isUploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadTags, setUploadTags] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  // Состояние меню действий
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [actionMenuAnchor, setActionMenuAnchor] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<RagDocument | null>(null);

  // Хуки
  const { showToast } = useToast();
  const { data, isLoading, error } = useRagDocuments({ page: 1, size: 100 });
  const uploadMutation = useUploadRagDocument();
  const deleteMutation = useDeleteRagDocument();

  // Обработчики событий
  const handleUpload = async () => {
    if (uploadFiles.length === 0) return;

    setIsUploading(true);
    try {
      const results = await Promise.allSettled(
        uploadFiles.map(file =>
          uploadMutation.mutateAsync({
            file,
            filename: file.name,
            tags: uploadTags,
          })
        )
      );

      const succeeded = results.filter(r => r.status === 'fulfilled');
      const failed = results.filter(r => r.status === 'rejected');

      if (succeeded.length > 0) {
        showToast(`Загрузка начата: ${succeeded.length} файлов`, 'success');
      }

      if (failed.length > 0) {
        console.error('Some uploads failed:', failed);
        showToast(`Не удалось загрузить: ${failed.length} файлов`, 'error');
      }

      setUploadModalOpen(false);
      setUploadFiles([]);
      setUploadTags([]);
    } catch (error) {
      console.error('Upload failed:', error);
      showToast('Критическая ошибка при загрузке', 'error');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm('Удалить документ?')) return;

    try {
      await deleteMutation.mutateAsync(docId);
      setActionMenuOpen(false);
      showToast('Документ удален', 'success');
    } catch (error) {
      console.error('Delete failed:', error);
      showToast('Ошибка при удалении документа', 'error');
    }
  };

  const handleIngest = async (docId: string) => {
    try {
      await startRagIngest(docId);
      showToast('Ингест запущен', 'success');
    } catch (error) {
      console.error('Ingest failed:', error);
      showToast('Ошибка при запуске ингеста', 'error');
    }
  };

  const handleUpdateScope = async (
    docId: string,
    scope: 'local' | 'global'
  ) => {
    try {
      await updateRagDocumentScope(docId, scope);
      showToast(
        `Скоуп изменен на ${scope === 'local' ? 'локальный' : 'глобальный'}`,
        'success'
      );
      setActionMenuOpen(false);
    } catch (error) {
      console.error('Update scope failed:', error);
      showToast('Ошибка при изменении скоупа', 'error');
    }
  };

  const handleUpdateTags = async (docId: string, tags: string[]) => {
    try {
      await updateRagDocumentTags(docId, tags);
      showToast('Теги обновлены', 'success');
      setActionMenuOpen(false);
    } catch (error) {
      console.error('Update tags failed:', error);
      showToast('Ошибка при обновлении тегов', 'error');
    }
  };

  const handleEditTags = () => {
    if (!selectedDoc) return;

    const currentTags = selectedDoc.tags || [];
    const newTags = prompt(
      'Введите теги через запятую:',
      currentTags.join(', ')
    );
    if (newTags !== null) {
      const tagsList = newTags
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0);
      handleUpdateTags(selectedDoc.id, tagsList);
    }
  };

  // Status modal functions removed - now using tooltip

  const handleActionMenuOpen = useCallback(
    (doc: RagDocument, element: HTMLElement) => {
      const rect = element.getBoundingClientRect();
      const menuWidth = 200;
      const menuHeight = 300;

      // Position to top-right of button
      let x = rect.right + 8;
      if (rect.right + menuWidth + 16 > window.innerWidth) {
        x = rect.left - menuWidth - 8;
      }

      // Position above button
      let y = rect.top - menuHeight - 8;
      if (rect.top - menuHeight < 8) {
        // If doesn't fit above, position below
        y = rect.bottom + 8;
      }

      // Ensure we don't go off screen
      x = Math.max(8, Math.min(x, window.innerWidth - menuWidth - 8));
      y = Math.max(8, Math.min(y, window.innerHeight - menuHeight - 8));

      setSelectedDoc(doc);
      setActionMenuAnchor({ x, y });
      setActionMenuOpen(true);
    },
    []
  );

  // Фильтрация документов
  const documents = data?.items || [];

  const filteredDocuments = useMemo(() => {
    return documents.filter(doc => {
      const text = (
        (doc.name || '') +
        ' ' +
        (doc.agg_status || '') +
        ' ' +
        (doc.created_at || '') +
        ' ' +
        (doc.tags?.join(' ') || '')
      ).toLowerCase();

      if (searchQuery.trim() && !text.includes(searchQuery.toLowerCase())) {
        return false;
      }

      if (
        filters.name &&
        !(doc.name || '')
          .toLowerCase()
          .includes((filters.name || '').toLowerCase())
      ) {
        return false;
      }

      if (filters.status && doc.agg_status !== filters.status) {
        return false;
      }

      if (
        filters.tags &&
        !(doc.tags?.join(' ') || '')
          .toLowerCase()
          .includes((filters.tags || '').toLowerCase())
      ) {
        return false;
      }

      if (
        filters.created_at &&
        !(doc.created_at || '')
          .toLowerCase()
          .includes((filters.created_at || '').toLowerCase())
      ) {
        return false;
      }

      return true;
    });
  }, [documents, searchQuery, filters]);

  const hasAnyFilter = Object.values(filters).some(Boolean);

  return (
    <div className={styles.wrap}>
      <Card className={styles.card}>
        <div className={styles.header}>
          <div className={styles.title}>База знаний — документы</div>
          <div className={styles.controls}>
            <Input
              className={styles.search}
              placeholder="Поиск…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
            {hasAnyFilter && (
              <Badge onClick={() => setFilters({})}>Сбросить фильтры</Badge>
            )}
            <Button onClick={() => setUploadModalOpen(true)}>Добавить</Button>
          </div>
        </div>

        {isLoading ? (
          <div className={styles.loading}>Загрузка документов...</div>
        ) : error ? (
          <div className={styles.loading}>Ошибка загрузки документов</div>
        ) : (
          <DocumentList
            documents={filteredDocuments}
            onActionMenuOpen={handleActionMenuOpen}
            isAdmin={isAdmin}
          />
        )}
      </Card>

      {/* Модалка загрузки */}
      <Uploader
        isOpen={isUploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onUpload={handleUpload}
        files={uploadFiles}
        onFilesSelected={setUploadFiles}
        uploadTags={uploadTags}
        onUploadTagsChange={setUploadTags}
        isUploading={isUploading}
      />

      {/* Меню действий */}
      <Popover
        open={actionMenuOpen}
        onOpenChange={setActionMenuOpen}
        anchor={actionMenuAnchor || undefined}
        content={
          <div
            style={{ minWidth: 200, padding: '4px 0' }}
            onClick={e => e.stopPropagation()}
            onMouseDown={e => e.stopPropagation()}
          >
            <button
              className={`${styles.actionButton}`}
              onClick={e => {
                e.preventDefault();
                e.stopPropagation();
                if (selectedDoc) {
                  handleDelete(selectedDoc.id);
                }
                setActionMenuOpen(false);
              }}
              title="Удалить документ"
            >
              Удалить
            </button>
            <button
              className={`${styles.actionButton}`}
              onClick={e => {
                e.preventDefault();
                e.stopPropagation();
                if (selectedDoc) {
                  handleIngest(selectedDoc.id);
                }
                setActionMenuOpen(false);
              }}
              title="Запустить ингест документа"
            >
              Ингест
            </button>
            <button
              className={`${styles.actionButton}`}
              onClick={e => {
                e.preventDefault();
                e.stopPropagation();
                handleEditTags();
              }}
              title="Редактировать теги документа"
            >
              Редактировать теги
            </button>
            {selectedDoc?.scope === 'local' && (
              <button
                className={styles.actionButton}
                onClick={e => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (selectedDoc) {
                    if (
                      confirm(
                        'Перевести документ в глобальный скоуп? Это действие необратимо.'
                      )
                    ) {
                      handleUpdateScope(selectedDoc.id, 'global');
                    }
                  }
                }}
                title="Перевести документ в глобальный скоуп"
              >
                В глобальный скоуп
              </button>
            )}
          </div>
        }
      />
    </div>
  );
}

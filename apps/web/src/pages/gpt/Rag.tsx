import React, { useEffect, useMemo, useState } from 'react';
import Card from '@shared/ui/Card';
import Input from '@shared/ui/Input';
import Button from '@shared/ui/Button';
import Badge from '@shared/ui/Badge';
import Modal from '@shared/ui/Modal';
import Popover from '@shared/ui/Popover';
import {
  FilterIcon,
  MoreVerticalIcon,
  DownloadIcon,
  RefreshIcon,
  ArchiveIcon,
  TrashIcon,
} from '@shared/ui/Icon';
import { useAuth } from '@app/store/auth';
import Select from '@shared/ui/Select';
import FilePicker from '@shared/ui/FilePicker';
import * as rag from '@shared/api/rag';
import { RagDocument } from '@shared/api/types';
import styles from './Rag.module.css';

type ColKey = 'name' | 'status' | 'created_at' | 'tags';

export default function Rag() {
  const { user } = useAuth();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';
  const isEditor = (user?.role || '').toLowerCase() === 'editor';
  
  const [items, setItems] = useState<RagDocument[]>([]);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [filters, setFilters] = useState<Partial<Record<ColKey, string>>>({});
  const [pop, setPop] = useState<{
    open: boolean;
    col?: ColKey;
    anchor?: { x: number; y: number };
  }>({ open: false });
  const [openAdd, setOpenAdd] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadTags, setUploadTags] = useState<string[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<RagDocument | null>(null);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [actionMenuAnchor, setActionMenuAnchor] = useState<{ x: number; y: number } | null>(null);

  async function refresh() {
    const res = await rag.listDocs({ page: 1, size: 100 });
    setItems(res.items || []);
  }

  useEffect(() => {
    refresh();
  }, []);

  const rows = useMemo(() => {
    return (items || []).filter(t => {
      const text = (
        (t.name || '') +
        ' ' +
        (t.status || '') +
        ' ' +
        (t.created_at || '') +
        ' ' +
        (t.tags?.join(' ') || '')
      ).toLowerCase();
      if (q.trim() && !text.includes(q.toLowerCase())) return false;
      if (
        filters.name &&
        !(t.name || '')
          .toLowerCase()
          .includes((filters.name || '').toLowerCase())
      )
        return false;
      if (filters.status && t.status !== filters.status) return false;
      if (
        filters.tags &&
        !(t.tags?.join(' ') || '')
          .toLowerCase()
          .includes((filters.tags || '').toLowerCase())
      )
        return false;
      if (
        filters.created_at &&
        !(t.created_at || '')
          .toLowerCase()
          .includes((filters.created_at || '').toLowerCase())
      )
        return false;
      return true;
    });
  }, [items, q, filters]);

  function openFilter(col: ColKey, el: HTMLElement) {
    const r = el.getBoundingClientRect();
    setPop({ open: true, col, anchor: { x: r.left, y: r.bottom + 6 } });
  }
  function clearAll() {
    setFilters({});
    setPop({ open: false });
  }

  async function doUpload() {
    if (!file) return;
    setBusy(true);
    try {
      await rag.uploadFile(file, file.name, uploadTags);
      setOpenAdd(false);
      setFile(null);
      setUploadTags([]);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const handleDownload = async (
    doc: RagDocument,
    kind: 'original' | 'canonical' = 'original'
  ) => {
    try {
      const res = await rag.downloadRagFile(doc.id, kind);
      if (res.url) {
        window.open(res.url, '_blank');
      }
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const handleArchive = async (doc: RagDocument) => {
    try {
      await rag.archiveRagDocument(doc.id);
      await refresh();
    } catch (error) {
      console.error('Archive failed:', error);
    }
  };

  const handleDelete = async (doc: RagDocument) => {
    if (!confirm('Удалить документ?')) return;
    try {
      await rag.deleteRagDocument(doc.id);
      await refresh();
    } catch (error) {
      console.error('Delete failed:', error);
    }
  };

  const handleReindex = async (doc: RagDocument) => {
    if (!confirm('Переиндексировать документ?')) return;
    try {
      await rag.reindexRagDocument(doc.id);
      await refresh();
    } catch (error) {
      console.error('Reindex failed:', error);
      alert('Ошибка переиндексации');
    }
  };

  const handleScopeChange = async (doc: RagDocument, newScope: 'local' | 'global') => {
    try {
      await rag.updateRagDocumentScope(doc.id, newScope);
      await refresh();
    } catch (error) {
      console.error('Scope change failed:', error);
      alert('Ошибка изменения скоупа');
    }
  };

  const handleVectorize = async (doc: RagDocument, model: string) => {
    try {
      await rag.vectorizeRagDocument(doc.id, model);
      await refresh();
    } catch (error) {
      console.error('Vectorization failed:', error);
      alert('Ошибка векторизации');
    }
  };

  const handleMerge = async (doc: RagDocument) => {
    if (!confirm('Объединить чанки документа?')) return;
    try {
      await rag.mergeRagDocument(doc.id);
      await refresh();
    } catch (error) {
      console.error('Merge failed:', error);
      alert('Ошибка объединения');
    }
  };

  const handleOptimize = async (doc: RagDocument) => {
    if (!confirm('Оптимизировать документ?')) return;
    try {
      await rag.optimizeRagDocument(doc.id);
      await refresh();
    } catch (error) {
      console.error('Optimization failed:', error);
      alert('Ошибка оптимизации');
    }
  };

  const handleAnalytics = async (doc: RagDocument) => {
    try {
      const analytics = await rag.getRagDocumentAnalytics(doc.id);
      alert(`Аналитика документа:\nПоисков: ${analytics.analytics.search_count}\nСредний скор: ${analytics.analytics.avg_score}\nЧанков: ${analytics.analytics.chunk_count}`);
    } catch (error) {
      console.error('Analytics failed:', error);
      alert('Ошибка получения аналитики');
    }
  };

  const openActionMenu = (doc: RagDocument, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    setSelectedDoc(doc);
    setActionMenuAnchor({ x: r.left, y: r.bottom + 6 });
    setActionMenuOpen(true);
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'queued':
        return 'В очереди';
      case 'processing':
        return 'Обработка';
      case 'ready':
      case 'processed':
        return 'Готов';
      case 'error':
        return 'Ошибка';
      case 'archived':
        return 'Архив';
      default:
        return status;
    }
  };

  const getScopeText = (scope: string) => {
    switch (scope) {
      case 'local':
        return 'Локальный';
      case 'global':
        return 'Глобальный';
      default:
        return scope;
    }
  };

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
              value={q}
              onChange={e => setQ(e.target.value)}
            />
            {hasAnyFilter && <Badge onClick={clearAll}>Сбросить фильтры</Badge>}
            <Button onClick={() => setOpenAdd(true)}>Добавить</Button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className="table">
            <thead>
              <tr>
                <th>
                  Название{' '}
                  <button
                    className="icon"
                    type="button"
                    aria-label="Фильтр по названию"
                    onClick={e => openFilter('name', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>
                  Статус{' '}
                  <button
                    className="icon"
                    type="button"
                    aria-label="Фильтр по статусу"
                    onClick={e => openFilter('status', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>
                  Теги{' '}
                  <button
                    className="icon"
                    type="button"
                    aria-label="Фильтр по тегам"
                    onClick={e => openFilter('tags', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>Скоуп</th>
                <th>
                  Создано{' '}
                  <button
                    className="icon"
                    type="button"
                    aria-label="Фильтр по дате создания"
                    onClick={e => openFilter('created_at', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(t => (
                <tr key={t.id}>
                  <td className="muted">{t.name || '—'}</td>
                  <td>
                    <Badge
                      tone={
                        t.status === 'ready'
                          ? 'success'
                          : t.status === 'error'
                            ? 'danger'
                            : t.status === 'processing'
                              ? 'warn'
                              : 'neutral'
                      }
                    >
                      {getStatusText(t.status || 'unknown')}
                    </Badge>
                  </td>
                  <td>{t.tags?.join(', ') || '—'}</td>
                  <td>
                    <Badge tone={t.scope === 'global' ? 'success' : 'neutral'}>
                      {getScopeText(t.scope)}
                    </Badge>
                  </td>
                  <td className="muted">{t.created_at || '—'}</td>
                  <td>
                    <button
                      className="icon"
                      type="button"
                      aria-label="Действия"
                      onClick={e => openActionMenu(t, e.currentTarget)}
                      style={{ cursor: 'pointer' }}
                    >
                      <MoreVerticalIcon />
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    Нет записей
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal
        open={openAdd}
        onClose={() => setOpenAdd(false)}
        title="Новый документ"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpenAdd(false)}>
              Отмена
            </Button>
            <Button onClick={doUpload} disabled={busy || !file}>
              Загрузить
            </Button>
          </>
        }
      >
        <div className="stack">
          <FilePicker
            onFileSelected={setFile}
            accept=".txt,.pdf,.doc,.docx,.md,.rtf,.odt"
            selectedFile={file}
            label="Выбрать файл"
          />
          <div>
            <label>Теги (опционально):</label>
            <Input
              placeholder="Введите теги через запятую..."
              value={uploadTags.join(', ')}
              onChange={e =>
                setUploadTags(
                  e.target.value
                    .split(',')
                    .map(t => t.trim())
                    .filter(Boolean)
                )
              }
            />
          </div>
        </div>
      </Modal>

      {/* Action Menu Popover */}
      <Popover
        open={actionMenuOpen}
        onOpenChange={setActionMenuOpen}
        anchor={actionMenuAnchor}
        content={
          selectedDoc && (
            <div style={{ minWidth: 180, padding: '4px 0' }}>
              {/* Scope Change - Editor/Admin only */}
              {(isEditor || isAdmin) && (
                <button
                  className={styles.actionButton}
                  onClick={() => {
                    const newScope = selectedDoc.scope === 'local' ? 'global' : 'local';
                    handleScopeChange(selectedDoc, newScope);
                    setActionMenuOpen(false);
                  }}
                >
                  {selectedDoc.scope === 'local' ? 'Перевести в глобальный' : 'Перевести в локальный'}
                </button>
              )}

              {/* Download Actions */}
              {selectedDoc.status === 'ready' && (
                <button
                  className={styles.actionButton}
                  onClick={() => {
                    handleDownload(selectedDoc, 'original');
                    setActionMenuOpen(false);
                  }}
                >
                  Скачать документ
                </button>
              )}

              {/* Archive - Editor/Admin only */}
              {(isEditor || isAdmin) && (
                <button
                  className={styles.actionButton}
                  onClick={() => {
                    handleArchive(selectedDoc);
                    setActionMenuOpen(false);
                  }}
                >
                  Архивировать
                </button>
              )}

              {/* Admin-only Actions */}
              {isAdmin && (
                <>
                  <hr style={{ margin: '8px 0', border: 'none', borderTop: '1px solid var(--color-border)' }} />
                  <button
                    className={styles.actionButton}
                    onClick={() => {
                      handleReindex(selectedDoc);
                      setActionMenuOpen(false);
                    }}
                  >
                    Переиндексировать
                  </button>
                  <button
                    className={styles.actionButton}
                    onClick={() => {
                      handleVectorize(selectedDoc, 'all-MiniLM-L6-v2');
                      setActionMenuOpen(false);
                    }}
                  >
                    Векторизовать
                  </button>
                  <button
                    className={styles.actionButton}
                    onClick={() => {
                      handleMerge(selectedDoc);
                      setActionMenuOpen(false);
                    }}
                  >
                    Объединить чанки
                  </button>
                  <button
                    className={styles.actionButton}
                    onClick={() => {
                      handleOptimize(selectedDoc);
                      setActionMenuOpen(false);
                    }}
                  >
                    Оптимизировать
                  </button>
                  <button
                    className={styles.actionButton}
                    onClick={() => {
                      handleAnalytics(selectedDoc);
                      setActionMenuOpen(false);
                    }}
                  >
                    Аналитика
                  </button>
                </>
              )}

              {/* Delete Action - Editor/Admin only */}
              {(isEditor || isAdmin) && (
                <>
                  <hr style={{ margin: '8px 0', border: 'none', borderTop: '1px solid var(--color-border)' }} />
                  <button
                    className={styles.actionButton}
                    onClick={() => {
                      handleDelete(selectedDoc);
                      setActionMenuOpen(false);
                    }}
                  >
                    Удалить
                  </button>
                </>
              )}
            </div>
          )
        }
      />

      <Popover
        trigger={<div />}
        content={
          <div className="stack" style={{ minWidth: 260 }}>
            {pop.col === 'status' ? (
              <Select
                value={filters.status || ''}
                onChange={e =>
                  setFilters(f => ({
                    ...f,
                    status: (e.target as HTMLSelectElement).value || undefined,
                  }))
                }
              >
                <option value="">Любой</option>
                <option value="queued">В очереди</option>
                <option value="processing">Обработка</option>
                <option value="ready">Готов</option>
                <option value="error">Ошибка</option>
                <option value="archived">Архив</option>
              </Select>
            ) : (
              <Input
                placeholder="Фильтр…"
                value={(filters[pop.col as ColKey] || '') as string}
                onChange={e => {
                  const val = e.target.value;
                  const col = pop.col as ColKey;
                  setFilters(f => ({
                    ...f,
                    [col]: (val || '').trim() || undefined,
                  }));
                }}
              />
            )}
            <div
              style={{
                display: 'flex',
                gap: 8,
                justifyContent: 'space-between',
              }}
            >
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const col = pop.col as ColKey;
                  setFilters(f => ({ ...f, [col]: undefined }));
                }}
              >
                Очистить
              </Button>
              <Button size="sm" onClick={() => setPop({ open: false })}>
                Применить
              </Button>
            </div>
          </div>
        }
        align="end"
      />
    </div>
  );
}

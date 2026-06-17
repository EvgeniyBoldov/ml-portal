/**
 * CollectionDataPage - View and manage collection data
 * Supports two modes:
 *   - table: tabular data with CSV upload
 *   - document: RAG document list with StatusModal, bulk actions, upload
 */
import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Checkbox from '@shared/ui/Checkbox';
import Badge from '@shared/ui/Badge';
import Modal from '@shared/ui/Modal';
import { DropdownMenu } from '@shared/ui/DropdownMenu';
import { Skeleton } from '@shared/ui/Skeleton';
import { Icon, MoreVerticalIcon } from '@shared/ui/Icon';
import { useToast } from '@shared/ui/Toast';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import {
  collectionsApi,
  type Collection,
  type CollectionDocument,
  type CollectionDocumentsResponse,
  type CollectionTemplate,
} from '@shared/api/collections';
import { ApiError } from '@shared/api/errors';
import { StatusModalNew } from '@/domains/rag/components/StatusModalNew';
import { qk } from '@shared/api/keys';
import { SSEClient, type SSEMessage } from '@shared/lib/sse';
import { buildFileDownloadUrl } from '@shared/api/files';
import { summarizeTemplateSchema } from '@shared/lib/templateSchemaSummary';
import TemplateStatusModal from './TemplateStatusModal';
import styles from './CollectionDataPage.module.css';

const PAGE_SIZES = [25, 50, 100];

// ─── Shared header ──────────────────────────────────────────────
interface CollectionHeaderProps {
  collection: Collection;
  total: number;
  right: React.ReactNode;
}

function CollectionHeader({ collection, total, right }: CollectionHeaderProps) {
  const navigate = useNavigate();
  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <button
          className={styles.backBtn}
          onClick={() => navigate('/gpt/collections')}
          title="Назад"
        >
          <Icon name="chevron-left" size={20} />
        </button>
        <div className={styles.titleBlock}>
          <h1 className={styles.title}>{collection.name}</h1>
          <div className={styles.subtitle}>
            <span>{collection.slug}</span>
            {collection.collection_type === 'document' ? (
              <Badge tone="warn">Документы</Badge>
            ) : collection.collection_type === 'template' ? (
              <Badge tone="success">Шаблоны</Badge>
            ) : (
              <>
                {collection.has_vector_search && (
                  <Badge tone="success">Vector</Badge>
                )}
              </>
            )}
            <span>{total.toLocaleString()} записей</span>
          </div>
        </div>
      </div>
      <div className={styles.headerRight}>{right}</div>
    </header>
  );
}

// ─── Table collection view ────────────────────────────────────────
interface TableViewProps {
  collection: Collection;
  slug: string;
}

function TableCollectionView({ collection, slug }: TableViewProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [activeExportId, setActiveExportId] = useState<string | null>(null);
  const isReadOnly = Boolean(collection.is_readonly);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const offset = (page - 1) * pageSize;
  const { data: dataResult, isLoading: dataLoading, refetch } = useQuery({
    queryKey: qk.collections.data(slug, { limit: pageSize, offset }),
    queryFn: () =>
      collectionsApi.getData(slug, {
        limit: pageSize,
        offset,
        search: debouncedSearch || undefined,
      }),
    enabled: !!slug,
  });

  const rows = dataResult?.items ?? [];
  const total = dataResult?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  const rowIds = useMemo(() => rows.map((row) => String(row.id)), [rows]);
  const allRowsSelected = rowIds.length > 0 && rowIds.every((id) => selectedIds.has(id));
  const someRowsSelected = rowIds.some((id) => selectedIds.has(id));

  useEffect(() => {
    setSelectedIds((prev) => {
      const visibleIds = new Set(rowIds);
      const next = new Set<string>(Array.from(prev).filter((id) => visibleIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [rowIds]);

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => collectionsApi.deleteRows(slug, ids),
    onSuccess: data => {
      showToast(`Удалено ${data.deleted} записей`, 'success');
      setSelectedIds(new Set<string>());
      queryClient.invalidateQueries({ queryKey: ['collections', 'data', slug] });
      queryClient.invalidateQueries({ queryKey: ['collections', 'detail', slug] });
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка удаления', 'error');
    },
  });

  const handleSelectAll = useCallback(() => {
    setSelectedIds(allRowsSelected ? new Set<string>() : new Set(rowIds));
  }, [allRowsSelected, rowIds]);

  const handleSelectRow = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set<string>(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleDeleteSelected = useCallback(() => {
    const ids = Array.from(selectedIds);
    showConfirmDialog({
      title: `Удалить ${ids.length} записей?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Действие необратимо"
          description="Выбранные записи будут удалены безвозвратно."
        />
      ),
      onConfirm: async () => {
        await deleteMutation.mutateAsync(ids);
      },
    });
  }, [selectedIds, showConfirmDialog, deleteMutation]);

  const handleUpload = async () => {
    if (!uploadFile || !slug) return;
    setUploading(true);
    try {
      const result = await collectionsApi.uploadCSV(slug, uploadFile, { skip_errors: true });
      showToast(`Загружено ${result.inserted_rows} записей`, 'success');
      if (result.errors.length > 0) {
        showToast(`${result.errors.length} записей пропущено из-за ошибок`, 'warning');
      }
      setUploadModalOpen(false);
      setUploadFile(null);
      refetch();
      queryClient.invalidateQueries({ queryKey: ['collections', 'detail', slug] });
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Ошибка загрузки', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleDownloadTemplate = () => {
    window.open(collectionsApi.downloadTemplate(slug), '_blank');
  };

  const pollExportReady = useCallback(async (exportId: string) => {
    const maxAttempts = 120;
    for (let i = 0; i < maxAttempts; i += 1) {
      const status = await collectionsApi.getCsvExportStatus(slug, exportId);
      if (status.status === 'ready') {
        const href = status.download_url || (status.file_id ? buildFileDownloadUrl(status.file_id) : '');
        if (href) {
          window.open(href, '_blank', 'noopener,noreferrer');
        }
        return;
      }
      if (status.status === 'failed') {
        throw new Error(status.error || 'Экспорт завершился с ошибкой');
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error('Превышено время ожидания экспорта');
  }, [slug]);

  const handleExportCsv = useCallback(async () => {
    if (exporting || isReadOnly) return;
    setExporting(true);
    try {
      const started = await collectionsApi.startCsvExport(slug);
      setActiveExportId(started.export_id);
      showToast('Экспорт запущен', 'success');
      await pollExportReady(started.export_id);
      showToast('CSV готов', 'success');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Ошибка экспорта CSV', 'error');
    } finally {
      setExporting(false);
      setActiveExportId(null);
    }
  }, [exporting, isReadOnly, pollExportReady, showToast, slug]);

  const truncateText = (text: unknown, maxLen = 100): string => {
    if (text === null || text === undefined) return '—';
    const str = String(text);
    return str.length <= maxLen ? str : str.substring(0, maxLen) + '...';
  };

  const fields = useMemo(
    () => Array.isArray(collection?.fields) ? collection.fields : [],
    [collection?.fields],
  );

  const headerRight = (
    <>
      <Input
        placeholder="Поиск..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className={styles.search}
      />
      {!isReadOnly && (
        <>
          <Button
            variant="danger"
            onClick={handleDeleteSelected}
            disabled={selectedIds.size === 0 || deleteMutation.isPending}
          >
            <Icon name="trash" size={16} />
            Удалить
          </Button>
          <Button variant="outline" onClick={handleDownloadTemplate}>
            <Icon name="download" size={16} />
            Шаблон CSV
          </Button>
          <Button variant="outline" onClick={handleExportCsv} disabled={exporting}>
            <Icon name="download" size={16} />
            {exporting ? (activeExportId ? 'Экспортируется...' : 'Запуск...') : 'Экспорт CSV'}
          </Button>
          <Button onClick={() => setUploadModalOpen(true)}>
            <Icon name="upload" size={16} />
            Загрузить CSV
          </Button>
        </>
      )}
    </>
  );

  return (
    <>
      <CollectionHeader collection={collection} total={total} right={headerRight} />

      <div className={styles.tableContainer}>
        {dataLoading ? (
          <div className={styles.loading}>
            <Skeleton width="100%" height={300} />
          </div>
        ) : rows.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <Icon name="file-text" size={48} />
            </div>
            <div className={styles.emptyTitle}>
              {debouncedSearch ? 'Ничего не найдено' : 'Нет данных'}
            </div>
            <p className={styles.emptyText}>
              {debouncedSearch
                ? 'Попробуйте изменить поисковый запрос'
                : isReadOnly
                  ? 'Нет данных для отображения'
                  : 'Загрузите данные через CSV файл'}
            </p>
            {!debouncedSearch && !isReadOnly && (
              <Button onClick={() => setUploadModalOpen(true)}>
                <Icon name="upload" size={16} />
                Загрузить CSV
              </Button>
            )}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                {!isReadOnly && (
                  <th className={styles.checkboxCol}>
                    <input
                      type="checkbox"
                      checked={allRowsSelected}
                      ref={(input) => {
                        if (input) input.indeterminate = someRowsSelected && !allRowsSelected;
                      }}
                      onChange={handleSelectAll}
                    />
                  </th>
                )}
                {fields.map((field) => (
                  <th key={field.name}>{field.description || field.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const rowId = String(row.id);
                const isSelected = selectedIds.has(rowId);
                return (
                  <tr key={rowId} className={!isReadOnly && isSelected ? styles.selected : undefined}>
                    {!isReadOnly && (
                      <td className={styles.checkboxCol}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => handleSelectRow(rowId)}
                        />
                      </td>
                    )}
                    {fields.map((field) => (
                      <td key={field.name} title={String(row[field.name] ?? '')}>
                        <span className={styles.cellTruncate}>
                          {truncateText(row[field.name] ?? '')}
                        </span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {total > 0 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>
            Показано {offset + 1}–{Math.min(offset + pageSize, total)} из{' '}
            {total.toLocaleString()}
          </div>
          <div className={styles.paginationControls}>
            <button className={styles.paginationBtn} onClick={() => setPage(1)} disabled={page === 1}>
              <Icon name="chevrons-left" size={16} />
            </button>
            <button className={styles.paginationBtn} onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
              <Icon name="chevron-left" size={16} />
            </button>
            <span style={{ margin: '0 8px', fontSize: 13 }}>
              Страница {page} из {totalPages}
            </span>
            <button className={styles.paginationBtn} onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              <Icon name="chevron-right" size={16} />
            </button>
            <button className={styles.paginationBtn} onClick={() => setPage(totalPages)} disabled={page === totalPages}>
              <Icon name="chevrons-right" size={16} />
            </button>
          </div>
          <div className={styles.pageSize}>
            <span>Показывать:</span>
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {PAGE_SIZES.map(size => <option key={size} value={size}>{size}</option>)}
            </select>
          </div>
        </div>
      )}

      {!isReadOnly && (
        <Modal
          open={uploadModalOpen}
          onClose={() => { setUploadModalOpen(false); setUploadFile(null); }}
          title="Загрузка CSV"
        >
          <div style={{ padding: 24 }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) setUploadFile(f); }}
              style={{ display: 'none' }}
            />
            {!uploadFile ? (
              <div className={styles.uploadZone} onClick={() => fileInputRef.current?.click()}>
                <div className={styles.uploadIcon}><Icon name="upload" size={48} /></div>
                <div className={styles.uploadText}>Нажмите или перетащите CSV файл</div>
                <div className={styles.uploadHint}>Поддерживается UTF-8, разделитель — запятая</div>
              </div>
            ) : (
              <div>
                <div style={{ marginBottom: 16 }}><strong>Файл:</strong> {uploadFile.name}</div>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                  <Button variant="outline" onClick={() => setUploadFile(null)} disabled={uploading}>Отмена</Button>
                  <Button onClick={handleUpload} disabled={uploading}>
                    {uploading ? 'Загрузка...' : 'Загрузить'}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

// ─── Document collection view ───────────────────────────────────
type DocStatusFilter = 'all' | 'ready' | 'processing' | 'failed' | 'uploaded';
type DocSortKey = 'name' | 'created_at' | 'agg_status';
type DocSortDir = 'asc' | 'desc';

const PROCESSING_STATUSES = ['processing', 'embedding', 'chunked', 'normalized'];

interface DocumentViewProps {
  collection: Collection;
}

function DocumentCollectionView({ collection }: DocumentViewProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const collectionSseRef = useRef<SSEClient | null>(null);
  const invalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const openModalDocIdRef = useRef<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<DocStatusFilter>('all');
  const [sortKey, setSortKey] = useState<DocSortKey>('created_at');
  const [sortDir, setSortDir] = useState<DocSortDir>('desc');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [statusModalDocId, setStatusModalDocId] = useState<string | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadMetaFields, setUploadMetaFields] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const collectionId = collection.id;

  const { data: uploadPolicy } = useQuery({
    queryKey: ['collections', 'document-upload-policy'],
    queryFn: () => collectionsApi.getDocumentUploadPolicy(),
  });

  const uploadAccept = useMemo(() => {
    const list = uploadPolicy?.allowed_extensions ?? ['txt', 'md', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'];
    return list.map((ext) => (ext.startsWith('.') ? ext : `.${ext}`)).join(',');
  }, [uploadPolicy]);
  const uploadHint = useMemo(() => {
    const list = uploadPolicy?.allowed_extensions ?? ['txt', 'md', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'];
    return `Поддерживаются: ${list.map((ext) => ext.toUpperCase()).join(', ')}`;
  }, [uploadPolicy]);

  const validateDocumentFiles = useCallback((files: File[]): File[] => {
    const maxBytes = uploadPolicy?.max_bytes ?? 50 * 1024 * 1024;
    const allowedExtensions = new Set(
      (uploadPolicy?.allowed_extensions ?? ['txt', 'md', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'])
        .map((item) => item.toLowerCase().replace(/^\./, ''))
    );
    const mimeByExt = uploadPolicy?.allowed_content_types_by_extension ?? {};
    const valid: File[] = [];
    const errors: string[] = [];

    for (const file of files) {
      const fileName = (file.name || '').toLowerCase();
      const dotIdx = fileName.lastIndexOf('.');
      const ext = dotIdx >= 0 ? fileName.slice(dotIdx + 1) : '';
      if (!ext || !allowedExtensions.has(ext)) {
        errors.push(`Файл "${file.name}" не поддерживается`);
        continue;
      }
      if (file.size > maxBytes) {
        errors.push(`Файл "${file.name}" превышает лимит ${(maxBytes / 1024 / 1024).toFixed(0)} МБ`);
        continue;
      }
      const mime = (file.type || '').toLowerCase();
      const allowedMime = mimeByExt[ext];
      if (mime && Array.isArray(allowedMime) && allowedMime.length > 0 && !allowedMime.includes(mime)) {
        errors.push(`Файл "${file.name}" имеет неподдерживаемый MIME: ${mime}`);
        continue;
      }
      valid.push(file);
    }

    if (errors.length > 0) {
      setUploadError(errors[0]);
      showToast(errors[0], 'error');
    } else {
      setUploadError(null);
    }
    return valid;
  }, [showToast, uploadPolicy]);

  // Extra fields defined by user at collection creation (non-system, non-file)
  const userDefinedFields = useMemo(() => {
    if (!collection.fields) return [];
    return collection.fields.filter(
      f => f.category === 'user' && f.data_type !== 'file' && f.name !== 'title' && f.name !== 'source' && f.name !== 'scope' && f.name !== 'tags',
    );
  }, [collection.fields]);

  // Metadata fields for table columns (non-file)
  const metaFields = useMemo(() => {
    if (!collection.fields) return [];
    return collection.fields
      .filter(f => f.data_type !== 'file' && f.category === 'user')
      .map(f => ({ name: f.name, label: f.description || f.name }));
  }, [collection.fields]);

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: qk.collections.documents(collectionId, { page: 1, size: 500 }),
    queryFn: () => collectionsApi.listDocuments(collectionId, { page: 1, size: 500 }),
    enabled: !!collectionId,
  });

  const invalidateDocs = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['collections', 'documents', collectionId] });
  }, [queryClient, collectionId]);

  const debouncedInvalidateDocs = useCallback(() => {
    if (invalidateTimerRef.current) return;
    invalidateTimerRef.current = setTimeout(() => {
      invalidateTimerRef.current = null;
      void queryClient.invalidateQueries({ queryKey: ['collections', 'documents', collectionId] });
    }, 500);
  }, [queryClient, collectionId]);

  const documents = docsData?.items ?? [];
  const totalDocs = docsData?.total ?? 0;

  // Stats
  const stats = useMemo(() => {
    const counts = { total: documents.length, ready: 0, processing: 0, failed: 0, uploaded: 0 };
    documents.forEach(doc => {
      const s = doc.agg_status || 'uploaded';
      if (s === 'ready') counts.ready++;
      else if (PROCESSING_STATUSES.includes(s)) counts.processing++;
      else if (s === 'failed') counts.failed++;
      else counts.uploaded++;
    });
    return counts;
  }, [documents]);

  const statCards: { label: string; value: number; color: string; filter: DocStatusFilter }[] = [
    { label: 'Всего', value: stats.total, color: 'neutral', filter: 'all' },
    { label: 'Готово', value: stats.ready, color: 'success', filter: 'ready' },
    { label: 'В обработке', value: stats.processing, color: 'warning', filter: 'processing' },
    { label: 'Ошибки', value: stats.failed, color: 'danger', filter: 'failed' },
  ];

  // Filter & sort
  const filteredDocuments = useMemo(() => {
    let result = [...documents];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(doc =>
        (doc.name || '').toLowerCase().includes(q) ||
        (doc.tags?.join(' ') || '').toLowerCase().includes(q)
      );
    }

    if (statusFilter !== 'all') {
      result = result.filter(doc => {
        const s = doc.agg_status || 'uploaded';
        if (statusFilter === 'ready') return s === 'ready';
        if (statusFilter === 'processing') return PROCESSING_STATUSES.includes(s);
        if (statusFilter === 'failed') return s === 'failed';
        if (statusFilter === 'uploaded') return s === 'uploaded';
        return true;
      });
    }

    result.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'name') cmp = (a.name || '').localeCompare(b.name || '');
      else if (sortKey === 'created_at') cmp = (a.created_at || '').localeCompare(b.created_at || '');
      else if (sortKey === 'agg_status') cmp = (a.agg_status || '').localeCompare(b.agg_status || '');
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [documents, searchQuery, statusFilter, sortKey, sortDir]);

  // Selection helpers
  const handleSort = (key: DocSortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('asc'); }
  };

  const handleSelectAll = () => {
    setSelectedIds(
      selectedIds.size === filteredDocuments.length
        ? new Set()
        : new Set(filteredDocuments.map(d => d.id))
    );
  };

  const handleSelect = (id: string) => {
    const s = new Set(selectedIds);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelectedIds(s);
  };

  // Selected docs computed
  const selectedDocs = useMemo(
    () => documents.filter(d => selectedIds.has(d.id)),
    [documents, selectedIds],
  );

  // Conditional bulk action visibility
  const canBulkIngest = selectedDocs.length > 0 && selectedDocs.some(
    d => (d.agg_status || 'uploaded') !== 'ready'
  );
  const canBulkArchive = selectedDocs.length > 0 && selectedDocs.every(
    d => d.status === 'active' || d.status === 'ready'
  );
  const canBulkDelete = selectedDocs.length > 0;

  useEffect(() => {
    if (!collectionId) return;
    const client = new SSEClient({
      url: collectionsApi.getStatusEventsUrl(collectionId),
      onMessage: (events: SSEMessage[]) => {
        let needsInvalidate = false;

        for (const event of events) {
          const payload = event.data as Record<string, unknown> | null;

          // Snapshot: patch React Query cache with current server state
          if (event.type === 'rag.snapshot') {
            const items = (payload?.items as Array<Record<string, unknown>>) ?? [];
            if (items.length > 0) {
              queryClient.setQueriesData<CollectionDocumentsResponse>(
                { queryKey: ['collections', 'documents', collectionId] },
                (old) => {
                  if (!old) return old;
                  const updated = old.items.map((doc) => {
                    const snap = items.find((i) => i.document_id === doc.id);
                    if (!snap) return doc;
                    return {
                      ...doc,
                      agg_status: (snap.agg_status as string) ?? doc.agg_status,
                    };
                  });
                  return { ...old, items: updated };
                },
              );
            }
            continue;
          }

          const eventType = String(payload?.event_type ?? '');
          if (
            eventType === 'aggregate_update' ||
            eventType === 'document_archived' ||
            eventType === 'document_unarchived' ||
            eventType === 'document_added' ||
            eventType === 'document_deleted' ||
            event.type === 'rag.deleted' ||
            event.type === 'rag.document_added' ||
            event.type === 'rag.document_deleted'
          ) {
            needsInvalidate = true;
          }
        }

        if (needsInvalidate) {
          debouncedInvalidateDocs();
          if (openModalDocIdRef.current) {
            void queryClient.invalidateQueries({ queryKey: ['collections', 'doc-status', openModalDocIdRef.current] });
          }
        }
      },
    });
    collectionSseRef.current = client;
    void client.connect();
    return () => {
      client.disconnect();
      collectionSseRef.current = null;
      if (invalidateTimerRef.current) {
        clearTimeout(invalidateTimerRef.current);
        invalidateTimerRef.current = null;
      }
    };
  }, [collectionId, queryClient, debouncedInvalidateDocs]);

  // Drag & drop
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(true);
  }, []);
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
  }, []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const files = validateDocumentFiles(Array.from(e.dataTransfer.files));
    if (files.length > 0) {
      setUploadFiles(files);
      setUploadModalOpen(true);
    }
  }, [validateDocumentFiles]);

  // Upload
  const handleUpload = async () => {
    if (uploadFiles.length === 0) return;
    setUploading(true);
    try {
      const results = await Promise.allSettled(
        uploadFiles.map(file =>
          collectionsApi.uploadDocument(collectionId, {
            file,
            meta_fields: Object.keys(uploadMetaFields).length > 0 ? uploadMetaFields : undefined,
            auto_ingest: true,
          })
        )
      );
      const succeeded = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;
      if (succeeded > 0) showToast(`Загружено: ${succeeded} файлов`, 'success');
      if (failed > 0) showToast(`Ошибка загрузки: ${failed} файлов`, 'error');
      setUploadModalOpen(false);
      setUploadFiles([]);
      setUploadMetaFields({});
      setUploadError(null);
      invalidateDocs();
    } catch {
      showToast('Ошибка загрузки', 'error');
    } finally {
      setUploading(false);
    }
  };

  // Bulk actions
  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Удалить ${selectedIds.size} документов? Данные будут удалены из MinIO и БД.`)) return;
    try {
      await collectionsApi.deleteDocuments(collectionId, Array.from(selectedIds));
      showToast(`Удалено: ${selectedIds.size} документов`, 'success');
      setSelectedIds(new Set());
      invalidateDocs();
    } catch {
      showToast('Ошибка удаления', 'error');
    }
  };

  const handleBulkIngest = async () => {
    if (selectedIds.size === 0) return;
    try {
      const results = await Promise.allSettled(
        Array.from(selectedIds).map(id => collectionsApi.startDocIngest(collectionId, id))
      );
      let started = 0;
      let alreadyRunning = 0;
      let failed = 0;

      results.forEach(result => {
        if (result.status === 'fulfilled') {
          started += 1;
          return;
        }
        const error = result.reason;
        if (error instanceof ApiError && error.status === 409) {
          alreadyRunning += 1;
          return;
        }
        failed += 1;
      });

      if (started > 0) showToast(`Ингест запущен: ${started} документов`, 'success');
      if (alreadyRunning > 0) showToast(`Уже в обработке: ${alreadyRunning} документов`, 'info');
      if (failed > 0) showToast(`Ошибка запуска: ${failed} документов`, 'error');

      if (started > 0 || alreadyRunning > 0) {
        setSelectedIds(new Set());
        invalidateDocs();
      }
    } catch {
      showToast('Ошибка запуска ингеста', 'error');
    }
  };

  // Single doc actions
  const handleDelete = async (doc: CollectionDocument) => {
    if (!confirm(`Удалить "${doc.name}"? Данные будут удалены из MinIO и БД.`)) return;
    try {
      await collectionsApi.deleteDocuments(collectionId, [doc.id]);
      showToast('Документ удален', 'success');
      invalidateDocs();
    } catch {
      showToast('Ошибка удаления', 'error');
    }
  };

  const handleIngest = async (doc: CollectionDocument) => {
    try {
      await collectionsApi.startDocIngest(collectionId, doc.id);
      showToast('Ингест запущен', 'success');
      invalidateDocs();
    } catch {
      showToast('Ошибка запуска ингеста', 'error');
    }
  };

  const handleCancel = async (doc: CollectionDocument) => {
    try {
      await collectionsApi.stopDocIngest(collectionId, doc.id, 'pipeline');
      showToast('Обработка отменена', 'success');
      invalidateDocs();
    } catch {
      showToast('Ошибка отмены', 'error');
    }
  };

  // Status badge
  const getStatusBadge = (status: string) => {
    const map: Record<string, { tone: 'success' | 'warn' | 'danger' | 'info' | 'neutral'; label: string }> = {
      ready: { tone: 'success', label: 'Готов' },
      processing: { tone: 'warn', label: 'Обработка' },
      embedding: { tone: 'warn', label: 'Эмбеддинг' },
      chunked: { tone: 'info', label: 'Разбит' },
      normalized: { tone: 'info', label: 'Нормализован' },
      failed: { tone: 'danger', label: 'Ошибка' },
      uploaded: { tone: 'neutral', label: 'Загружен' },
    };
    const cfg = map[status] || { tone: 'neutral' as const, label: status };
    const isProc = PROCESSING_STATUSES.includes(status);
    return <Badge tone={cfg.tone} className={isProc ? styles.pulsing : ''}>{cfg.label}</Badge>;
  };

  const formatDate = (d: string | null) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return '—'; }
  };

  const renderMetaField = (value: unknown): string => {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'string') return value || '—';
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    try {
      return JSON.stringify(value);
    } catch {
      return '—';
    }
  };

  const headerRight = (
    <Button variant="primary" onClick={() => setUploadModalOpen(true)}>
      <Icon name="upload" size={16} />
      Загрузить
    </Button>
  );

  return (
    <>
      <CollectionHeader collection={collection} total={totalDocs} right={headerRight} />

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
      <div className={styles.docToolbar}>
        <div className={styles.docToolbarLeft}>
          <Input
            className={styles.search}
            placeholder="Поиск по имени или тегам..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
        <div className={styles.docToolbarRight}>
          {selectedIds.size > 0 && (
            <div className={styles.docBulkActions}>
              <span className={styles.docSelectedCount}>Выбрано: {selectedIds.size}</span>
              {canBulkIngest && (
                <Button variant="ghost" size="sm" onClick={handleBulkIngest}>
                  Запустить ингест
                </Button>
              )}
              {canBulkDelete && (
                <Button variant="danger" size="sm" onClick={handleBulkDelete}>
                  Удалить
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                Отменить
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Document table */}
      <div
        className={`${styles.tableContainer} ${isDragging ? styles.dragging : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {isDragging && (
          <div className={styles.dropOverlay}>
            <div className={styles.dropContent}>
              <Icon name="upload" size={48} />
              <span>Перетащите файлы для загрузки</span>
            </div>
          </div>
        )}

        {docsLoading ? (
          <div className={styles.docLoading}>
            <div className={styles.spinner} />
            <span>Загрузка документов...</span>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className={styles.docEmpty}>
          <span style={{ opacity: 0.3, display: 'inline-flex' }}>
            <Icon name="file-text" size={48} />
          </span>
            <h3>Документы не найдены</h3>
            <p>
              {searchQuery || statusFilter !== 'all'
                ? 'Попробуйте изменить фильтры'
                : 'Загрузите первый документ для начала работы'}
            </p>
            {!searchQuery && statusFilter === 'all' && (
              <Button onClick={() => setUploadModalOpen(true)}>Загрузить документ</Button>
            )}
          </div>
        ) : (
          <table className={styles.docTable}>
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
                  {sortKey === 'name' && <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />}
                </th>
                <th className={styles.sortable} onClick={() => handleSort('agg_status')}>
                  Статус
                  {sortKey === 'agg_status' && <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />}
                </th>
                <th>Размер</th>
                {metaFields.map(f => (
                  <th key={f.name}>{f.label}</th>
                ))}
                <th className={styles.sortable} onClick={() => handleSort('created_at')}>
                  Создан
                  {sortKey === 'created_at' && <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />}
                </th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map(doc => {
                const isProc = PROCESSING_STATUSES.includes(doc.agg_status || '');
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
                        onClick={() => { openModalDocIdRef.current = doc.id; setStatusModalDocId(doc.id); }}
                      >
                        {doc.name || 'Без имени'}
                      </button>
                    </td>
                    <td>
                      <button
                        className={styles.statusButton}
                        onClick={() => { openModalDocIdRef.current = doc.id; setStatusModalDocId(doc.id); }}
                      >
                        {getStatusBadge(doc.agg_status || 'uploaded')}
                      </button>
                    </td>
                    <td className={styles.muted}>
                      {doc.size_bytes ? `${(doc.size_bytes / 1024 / 1024).toFixed(2)} MB` : '—'}
                    </td>
                    {metaFields.map(f => (
                      <td key={f.name} className={styles.muted}>
                        {renderMetaField(doc.meta_fields?.[f.name])}
                      </td>
                    ))}
                    <td className={styles.muted}>{formatDate(doc.created_at)}</td>
                    <td>
                      <div className={styles.actions}>
                        {isProc ? (
                          <button className={styles.actionBtn} onClick={() => handleCancel(doc)} title="Отменить обработку">
                            <Icon name="x" size={16} />
                          </button>
                        ) : doc.agg_status !== 'ready' ? (
                          <button className={styles.actionBtn} onClick={() => handleIngest(doc)} title="Запустить ингест">
                            <Icon name="play" size={16} />
                          </button>
                        ) : null}
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

      {/* Upload modal */}
      <Modal
        open={uploadModalOpen}
        onClose={() => { setUploadModalOpen(false); setUploadFiles([]); setUploadMetaFields({}); setUploadError(null); }}
        title="Загрузка документов"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadModalOpen(false)}>Отмена</Button>
            <Button onClick={handleUpload} disabled={uploadFiles.length === 0 || uploading}>
              {uploading ? 'Загрузка...' : `Загрузить (${uploadFiles.length})`}
            </Button>
          </>
        }
      >
        <div className={styles.docUploadContent}>
          <div
            className={styles.dropZone}
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click(); } }}
          >
            <Icon name="upload" size={32} />
            <span>Нажмите или перетащите файлы</span>
            <span className={styles.dropZoneHint}>{uploadHint}</span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={uploadAccept}
            style={{ display: 'none' }}
            onChange={e => {
              const files = validateDocumentFiles(Array.from(e.target.files || []));
              if (files.length > 0) {
                setUploadFiles(prev => [...prev, ...files]);
              }
              if (e.target) e.target.value = '';
            }}
          />
          {uploadFiles.length > 0 && (
            <div className={styles.fileList}>
              {uploadFiles.map((file, idx) => (
                <div key={`${file.name}-${idx}`} className={styles.fileItem}>
                  <Icon name="file-text" size={16} />
                  <span className={styles.fileName}>{file.name}</span>
                  <span className={styles.fileSize}>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  <button
                    className={styles.fileRemove}
                    onClick={() => setUploadFiles(f => f.filter((_, i) => i !== idx))}
                  >
                    <Icon name="x" size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
          {userDefinedFields.length > 0 && (
            <div className={styles.metaFieldsGroup}>
              {userDefinedFields.map(f => {
                const dt = f.data_type;
                const label = (
                  <label>{f.description || f.name}{f.required && <span className={styles.required}> *</span>}</label>
                );
                if (dt === 'boolean') {
                  return (
                    <div key={f.name} className={styles.formGroup}>
                      <Checkbox
                        checked={uploadMetaFields[f.name] === 'true'}
                        onChange={checked =>
                          setUploadMetaFields(prev => ({ ...prev, [f.name]: String(checked) }))
                        }
                        label={f.description || f.name}
                      />
                    </div>
                  );
                }
                if (dt === 'integer') {
                  return (
                    <div key={f.name} className={styles.formGroup}>
                      {label}
                      <Input
                        type="number"
                        step={1}
                        placeholder="0"
                        value={uploadMetaFields[f.name] ?? ''}
                        onChange={e => setUploadMetaFields(prev => ({ ...prev, [f.name]: e.target.value }))}
                      />
                    </div>
                  );
                }
                if (dt === 'float') {
                  return (
                    <div key={f.name} className={styles.formGroup}>
                      {label}
                      <Input
                        type="number"
                        step="any"
                        placeholder="0.0"
                        value={uploadMetaFields[f.name] ?? ''}
                        onChange={e => setUploadMetaFields(prev => ({ ...prev, [f.name]: e.target.value }))}
                      />
                    </div>
                  );
                }
                if (dt === 'date') {
                  return (
                    <div key={f.name} className={styles.formGroup}>
                      {label}
                      <Input
                        type="date"
                        value={uploadMetaFields[f.name] ?? ''}
                        onChange={e => setUploadMetaFields(prev => ({ ...prev, [f.name]: e.target.value }))}
                      />
                    </div>
                  );
                }
                if (dt === 'datetime') {
                  return (
                    <div key={f.name} className={styles.formGroup}>
                      {label}
                      <Input
                        type="datetime-local"
                        value={uploadMetaFields[f.name] ?? ''}
                        onChange={e => setUploadMetaFields(prev => ({ ...prev, [f.name]: e.target.value }))}
                      />
                    </div>
                  );
                }
                return (
                  <div key={f.name} className={styles.formGroup}>
                    {label}
                    <Input
                      type="text"
                      placeholder={f.description || f.name}
                      value={uploadMetaFields[f.name] ?? ''}
                      onChange={e => setUploadMetaFields(prev => ({ ...prev, [f.name]: e.target.value }))}
                    />
                  </div>
                );
              })}
            </div>
          )}
          {uploadError && (
            <div className={styles.error}>{uploadError}</div>
          )}
        </div>
      </Modal>

      {/* Status Modal — reused from RAG without changes */}
      {statusModalDocId && (
        <StatusModalNew
          docId={statusModalDocId}
          docName={documents.find(d => d.id === statusModalDocId)?.name}
          onClose={() => { setStatusModalDocId(null); openModalDocIdRef.current = null; }}
          sseUrl={collectionsApi.getDocumentStatusEventsUrl(collectionId, statusModalDocId)}
          statusGraphUrl={`/collections/${collectionId}/docs/${statusModalDocId}/status-graph`}
          retryUrlPrefix={`/collections/${collectionId}/docs/${statusModalDocId}/ingest/retry`}
          stopUrlPrefix={`/collections/${collectionId}/docs/${statusModalDocId}/ingest/stop`}
        />
      )}
    </>
  );
}

type SchemaEditorState = {
  rowId: string;
  title: string;
  description: string;
} | null;

function TemplateSchemaEditorModal({
  open,
  title,
  draft,
  description,
  error,
  saving,
  onDraftChange,
  onDescriptionChange,
  onClose,
  onSave,
}: {
  open: boolean;
  title: string;
  draft: string;
  description: string;
  error: string | null;
  saving: boolean;
  onDraftChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="xl"
      className={styles.schemaEditorModal}
      bodyClassName={styles.schemaEditorBody}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button onClick={onSave} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </>
      }
    >
      <div className={styles.schemaEditorLayout}>
        <div className={styles.schemaEditorPane}>
          <div className={styles.schemaEditorLabel}>Схема</div>
          <textarea
            className={styles.schemaEditorTextarea}
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            spellCheck={false}
          />
        </div>
        <div className={styles.schemaEditorPane}>
          <div className={styles.schemaEditorLabel}>Описание</div>
          <textarea
            className={styles.schemaEditorDescription}
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            spellCheck={false}
            placeholder="Короткое семантическое описание шаблона..."
          />
        </div>
      </div>
      {error && <div className={styles.schemaEditorError}>{error}</div>}
    </Modal>
  );
}

// ─── Template collection view ───────────────────────────────────
interface TemplateViewProps {
  collection: Collection;
  slug: string;
}

function TemplateCollectionView({ collection, slug }: TemplateViewProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [schemaEditor, setSchemaEditor] = useState<SchemaEditorState>(null);
  const [schemaDraft, setSchemaDraft] = useState('');
  const [descriptionDraft, setDescriptionDraft] = useState('');
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [statusModalRow, setStatusModalRow] = useState<CollectionTemplate | null>(null);
  const [actionsMenu, setActionsMenu] = useState<{ row: CollectionTemplate; anchorEl: HTMLElement } | null>(null);

  const collectionId = collection.id;

  const { data: templatesData, isLoading: templatesLoading } = useQuery({
    queryKey: ['collections', 'templates', collectionId, { page: 1, size: 500 }],
    queryFn: () => collectionsApi.listTemplates(collectionId, { page: 1, size: 500 }),
    enabled: !!collectionId,
    refetchInterval: 3000,
  });

  const templates = templatesData?.items ?? [];
  const totalTemplates = templatesData?.total ?? 0;

  const filteredTemplates = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return templates;
      return templates.filter((item) => {
      const fileName = String((item.file as Record<string, unknown> | undefined)?.filename ?? '').toLowerCase();
      return (
        String(item.title ?? '').toLowerCase().includes(query)
        || String(item.description ?? '').toLowerCase().includes(query)
        || String(item.source ?? '').toLowerCase().includes(query)
        || String(item.template_version ?? '').toLowerCase().includes(query)
        || String(item.status ?? '').toLowerCase().includes(query)
        || fileName.includes(query)
      );
    });
  }, [searchQuery, templates]);

  const invalidateTemplates = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['collections', 'templates', collectionId] });
    void queryClient.invalidateQueries({ queryKey: ['collections', 'detail', slug] });
  }, [collectionId, queryClient, slug]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => collectionsApi.uploadTemplate(collectionId, { file }),
    onSuccess: () => {
      showToast('Шаблон загружен, анализ запущен', 'success');
      setUploadFile(null);
      setUploadModalOpen(false);
      invalidateTemplates();
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка загрузки шаблона', 'error');
    },
    onSettled: () => {
      setUploading(false);
    },
  });

  const saveSchemaMutation = useMutation({
    mutationFn: ({
      rowId,
      templateSchema,
      description,
    }: {
      rowId: string;
      templateSchema: Record<string, unknown>;
      description: string | null;
    }) =>
      collectionsApi.updateTemplate(collectionId, rowId, {
        template_schema: templateSchema,
        description,
      }),
    onSuccess: () => {
      showToast('Шаблон обновлен', 'success');
      setSchemaEditor(null);
      setSchemaDraft('');
      setDescriptionDraft('');
      setSchemaError(null);
      invalidateTemplates();
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка обновления схемы', 'error');
    },
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({
      rowId,
      status,
    }: {
      rowId: string;
      status: 'uploaded' | 'analyzed' | 'ready' | 'archived';
    }) =>
      collectionsApi.updateTemplate(collectionId, rowId, {
        status,
      }),
    onSuccess: (_, variables) => {
      const labelMap: Record<string, string> = {
        uploaded: 'Загружен',
        analyzed: 'Проанализирован',
        ready: 'Активирован',
        archived: 'Отправлен в архив',
      };
      showToast(labelMap[variables.status] || 'Статус обновлен', 'success');
      setActionsMenu(null);
      invalidateTemplates();
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка изменения статуса', 'error');
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: (rowIds: string[]) => collectionsApi.analyzeTemplates(collectionId, rowIds),
    onSuccess: (result) => {
      const queued = result.queued ?? 0;
      const missing = result.missing?.length ?? 0;
      if (queued > 0) showToast(`Анализ запущен: ${queued} шаблонов`, 'success');
      if (missing > 0) showToast(`Не найдены: ${missing} шаблонов`, 'info');
      setSelectedIds(new Set<string>());
      invalidateTemplates();
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка запуска анализа', 'error');
    },
  });

  const handleSelectAll = useCallback(() => {
    const visibleIds = filteredTemplates.map((item) => item.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set<string>() : new Set<string>(visibleIds));
  }, [filteredTemplates, selectedIds]);

  const handleSelectRow = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleUpload = useCallback(() => {
    if (!uploadFile) return;
    setUploading(true);
    uploadMutation.mutate(uploadFile);
  }, [uploadFile, uploadMutation]);

  const handleDeleteRows = useCallback(async (ids: string[]) => {
    if (ids.length === 0) return;
    await collectionsApi.deleteTemplates(collectionId, ids);
    showToast(`Удалено: ${ids.length} шаблонов`, 'success');
    setSelectedIds(new Set<string>());
    invalidateTemplates();
  }, [collectionId, invalidateTemplates, showToast]);

  const handleDeleteSelected = useCallback(() => {
    const ids = Array.from(selectedIds);
    showConfirmDialog({
      title: `Удалить ${ids.length} шаблонов?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Действие необратимо"
          description="Выбранные шаблоны будут удалены из коллекции."
        />
      ),
      onConfirm: async () => {
        await handleDeleteRows(ids);
      },
    });
  }, [handleDeleteRows, selectedIds, showConfirmDialog]);

  const handleAnalyzeSelected = useCallback(() => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    analyzeMutation.mutate(ids);
  }, [analyzeMutation, selectedIds]);

  const handleAnalyzeOne = useCallback((rowId: string) => {
    analyzeMutation.mutate([rowId]);
  }, [analyzeMutation]);

  const handleSetStatus = useCallback((rowId: string, status: 'ready' | 'archived') => {
    updateStatusMutation.mutate({ rowId, status });
  }, [updateStatusMutation]);

  const handleDeleteOne = useCallback((rowId: string, title: string) => {
    showConfirmDialog({
      title: `Удалить "${title}"?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Действие необратимо"
          description="Шаблон будет удалён из коллекции."
        />
      ),
      onConfirm: async () => {
        await handleDeleteRows([rowId]);
      },
    });
  }, [handleDeleteRows, showConfirmDialog]);

  const openSchemaEditor = useCallback((row: CollectionTemplate) => {
    setSchemaEditor({
      rowId: row.id,
      title: row.title || 'Редактирование шаблона',
      description: String(row.description ?? ''),
    });
    setSchemaDraft(JSON.stringify(row.template_schema ?? {}, null, 2));
    setDescriptionDraft(String(row.description ?? ''));
    setSchemaError(null);
  }, []);

  const openStatusModal = useCallback((row: CollectionTemplate) => {
    setStatusModalRow(row);
  }, []);

  const openActionsMenu = useCallback((row: CollectionTemplate, anchorEl: HTMLElement) => {
    setActionsMenu({ row, anchorEl });
  }, []);

  const closeActionsMenu = useCallback(() => {
    setActionsMenu(null);
  }, []);

  const handleDownload = useCallback((row: CollectionTemplate) => {
    const fileMeta = row.file as Record<string, unknown> | undefined;
    const directDownloadUrl = String(fileMeta?.download_url ?? '').trim();
    const fileId = String(fileMeta?.file_id ?? '').trim();
    const downloadUrl = directDownloadUrl || (fileId ? buildFileDownloadUrl(fileId) : '');
    if (!downloadUrl) {
      showToast('Оригинальный файл не найден', 'warning');
      return;
    }
    window.open(downloadUrl, '_blank', 'noopener,noreferrer');
  }, [showToast]);

  const handleSaveSchema = useCallback(() => {
    if (!schemaEditor?.rowId) return;
    try {
      const parsed = JSON.parse(schemaDraft) as Record<string, unknown>;
      setSchemaError(null);
      saveSchemaMutation.mutate({
        rowId: schemaEditor.rowId,
        templateSchema: parsed,
        description: descriptionDraft.trim() ? descriptionDraft.trim() : null,
      });
    } catch {
      setSchemaError('Некорректный JSON');
    }
  }, [descriptionDraft, saveSchemaMutation, schemaDraft, schemaEditor?.rowId]);

  const getTemplateStatusBadge = (row: CollectionTemplate) => {
    const status = String(row.status ?? 'uploaded').toLowerCase();
    const map: Record<string, { tone: 'success' | 'warn' | 'neutral' | 'info'; label: string }> = {
      uploaded: { tone: 'neutral', label: 'Загружен' },
      analyzed: { tone: 'info', label: 'Проанализирован' },
      ready: { tone: 'success', label: 'Готов' },
      archived: { tone: 'neutral', label: 'Архив' },
    };
    const cfg = map[status] ?? { tone: 'neutral' as const, label: status || '—' };
    return <Badge tone={cfg.tone}>{cfg.label}</Badge>;
  };

  const headerRight = (
    <>
      <Input
        className={styles.search}
        placeholder="Поиск по шаблонам..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
      />
      {selectedIds.size > 0 && (
        <Button variant="danger" onClick={handleDeleteSelected}>
          <Icon name="trash" size={16} />
          Удалить
        </Button>
      )}
      {selectedIds.size > 0 && (
        <Button variant="ghost" onClick={handleAnalyzeSelected} disabled={analyzeMutation.isPending}>
          <Icon name="sparkles" size={16} />
          {analyzeMutation.isPending ? 'Анализ...' : 'Запустить анализ'}
        </Button>
      )}
      <Button variant="primary" onClick={() => setUploadModalOpen(true)}>
        <Icon name="upload" size={16} />
        Загрузить шаблон
      </Button>
    </>
  );

  const visibleIds = filteredTemplates.map((item) => item.id);
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  return (
    <>
      <CollectionHeader collection={collection} total={totalTemplates} right={headerRight} />

      <div className={styles.tableContainer}>
        {templatesLoading ? (
          <div className={styles.loading}>
            <Skeleton width="100%" height={300} />
          </div>
        ) : filteredTemplates.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <Icon name="file-text" size={48} />
            </div>
            <div className={styles.emptyTitle}>
              {searchQuery ? 'Ничего не найдено' : 'Нет шаблонов'}
            </div>
            <p className={styles.emptyText}>
              {searchQuery ? 'Попробуйте изменить поисковый запрос' : 'Загрузите первый шаблон для начала работы'}
            </p>
            {!searchQuery && (
              <Button onClick={() => setUploadModalOpen(true)}>
                <Icon name="upload" size={16} />
                Загрузить шаблон
              </Button>
            )}
          </div>
        ) : (
          <table className={styles.docTable}>
            <thead>
              <tr>
                <th className={styles.checkboxCell}>
                  <input type="checkbox" checked={allSelected} onChange={handleSelectAll} />
                </th>
                <th>Название</th>
                <th>Статус</th>
                <th>Описание</th>
                <th>Версия</th>
                <th>Схема</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {filteredTemplates.map((row) => {
                return (
                  <tr key={row.id} className={selectedIds.has(row.id) ? styles.selected : ''}>
                    <td className={styles.checkboxCell}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(row.id)}
                        onChange={() => handleSelectRow(row.id)}
                      />
                    </td>
                    <td className={styles.nameCell}>
                      <button
                        type="button"
                        className={styles.templateTitleBtn}
                        onClick={() => openStatusModal(row)}
                        title="Открыть статус"
                      >
                        {row.title || 'Без названия'}
                      </button>
                    </td>
                    <td>{getTemplateStatusBadge(row)}</td>
                    <td className={`${styles.muted} ${styles.descriptionCell}`}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span>{row.description || '—'}</span>
                      </div>
                    </td>
                    <td className={styles.muted}>{row.template_version || '—'}</td>
                    <td>
                      <div className={styles.schemaCell}>
                        <input
                          className={styles.schemaPreviewInput}
                          type="text"
                          value={summarizeTemplateSchema(row.template_schema)}
                          readOnly
                        />
                      </div>
                    </td>
                    <td>
                      <div className={styles.actions}>
                        <button
                          type="button"
                          className={styles.actionBtn}
                          onClick={(e) => {
                            e.stopPropagation();
                            openActionsMenu(row, e.currentTarget);
                          }}
                          title="Действия"
                        >
                          <MoreVerticalIcon size={16} />
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

      <Modal
        open={uploadModalOpen}
        onClose={() => { setUploadModalOpen(false); setUploadFile(null); }}
        title="Загрузка шаблона"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadModalOpen(false)}>Отмена</Button>
            <Button onClick={handleUpload} disabled={!uploadFile || uploading}>
              {uploading ? 'Загрузка...' : 'Загрузить'}
            </Button>
          </>
        }
      >
        <div className={styles.docUploadContent}>
          <div
            className={styles.dropZone}
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
          >
            <Icon name="upload" size={32} />
            <span>Нажмите, чтобы выбрать файл шаблона</span>
            <span className={styles.dropZoneHint}>Поддерживаются Excel, Word и текстовые шаблоны</span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.xlsm,.docx,.doc,.txt,.md"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0] ?? null;
              setUploadFile(file);
              if (e.target) e.target.value = '';
            }}
          />
          {uploadFile && (
            <div className={styles.fileList}>
              <div className={styles.fileItem}>
                <Icon name="file-text" size={16} />
                <span className={styles.fileName}>{uploadFile.name}</span>
                <span className={styles.fileSize}>{(uploadFile.size / 1024 / 1024).toFixed(2)} MB</span>
                <button className={styles.fileRemove} onClick={() => setUploadFile(null)}>
                  <Icon name="x" size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      </Modal>

      <TemplateSchemaEditorModal
        open={Boolean(schemaEditor)}
        title={schemaEditor?.title || 'Редактирование схемы шаблона'}
        draft={schemaDraft}
        description={descriptionDraft}
        error={schemaError}
        saving={saveSchemaMutation.isPending}
        onDraftChange={setSchemaDraft}
        onDescriptionChange={setDescriptionDraft}
        onClose={() => { setSchemaEditor(null); setSchemaDraft(''); setDescriptionDraft(''); setSchemaError(null); }}
        onSave={handleSaveSchema}
      />

      <DropdownMenu
        isOpen={Boolean(actionsMenu?.row)}
        onClose={closeActionsMenu}
        anchorEl={actionsMenu?.anchorEl ?? null}
        items={actionsMenu?.row ? [
          {
            label: 'Скачать',
            onClick: () => handleDownload(actionsMenu.row),
            disabled: !String((actionsMenu.row.file as Record<string, unknown> | undefined)?.file_id ?? '').trim(),
          },
          {
            label: 'Редактировать',
            onClick: () => openSchemaEditor(actionsMenu.row),
          },
          {
            label: 'Анализ',
            onClick: () => handleAnalyzeOne(actionsMenu.row.id),
            disabled: analyzeMutation.isPending,
          },
          ...(String(actionsMenu.row.status ?? '').toLowerCase() === 'analyzed' || String(actionsMenu.row.status ?? '').toLowerCase() === 'archived'
            ? [{
                label: 'Активировать',
                onClick: () => handleSetStatus(actionsMenu.row.id, 'ready'),
              }]
            : []),
          ...((String(actionsMenu.row.status ?? '').toLowerCase() === 'ready')
            ? [{
                label: 'В архив',
                onClick: () => handleSetStatus(actionsMenu.row.id, 'archived'),
              }]
            : []),
          {
            label: 'Удалить',
            onClick: () => handleDeleteOne(actionsMenu.row.id, actionsMenu.row.title || 'Шаблон'),
            variant: 'danger',
          },
        ] : []}
      />

      {statusModalRow && (
        <TemplateStatusModal
          collectionId={collectionId}
          row={statusModalRow}
          onClose={() => setStatusModalRow(null)}
        />
      )}
    </>
  );
}

// ─── Main page component ────────────────────────────────────────
export default function CollectionDataPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const { data: collection, isLoading: collectionLoading } = useQuery({
    queryKey: ['collections', 'detail', slug],
    queryFn: () => collectionsApi.getBySlug(slug!),
    enabled: !!slug,
  });

  if (collectionLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>
          <Skeleton width={400} height={200} />
        </div>
      </div>
    );
  }

  if (!collection) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>
          <div className={styles.emptyTitle}>Коллекция не найдена</div>
          <Button onClick={() => navigate('/gpt/collections')}>
            Вернуться к списку
          </Button>
        </div>
      </div>
    );
  }

  const isDocument = collection.collection_type === 'document';
  const isTemplate = collection.collection_type === 'template';

  return (
    <div className={styles.page}>
      {isDocument ? (
        <DocumentCollectionView key={collection.id} collection={collection} />
      ) : isTemplate ? (
        <TemplateCollectionView key={collection.id} collection={collection} slug={slug!} />
      ) : (
        <TableCollectionView key={collection.id} collection={collection} slug={slug!} />
      )}
    </div>
  );
}

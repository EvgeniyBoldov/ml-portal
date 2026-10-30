/**
 * CollectionDataPage - View and manage collection data
 * Supports two modes:
 *   - table: tabular data with CSV upload
 *   - document: RAG document list with StatusModal, bulk actions, upload
 */
import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
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
  type CollectionCapabilities,
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
import GlossaryCollectionView from './GlossaryCollectionView';
import ExternalCollectionOverview from '../components/ExternalCollectionOverview';
import { memoryScopesApi } from '@/shared/api/memoryScopes';
import { CollectionLoadError } from '../components/CollectionLoadError';
import { capabilityReasonCopy } from '../capabilityReasonCopy';
import styles from './CollectionDataPage.module.css';

const PAGE_SIZES = [25, 50, 100];
type CapabilityRefreshReason = 'forbidden' | 'unavailable';
type CapabilityRefreshCallback = (reason?: CapabilityRefreshReason) => void | Promise<Collection | null>;

function isInactiveCollectionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && (
    error.code === 'collection_inactive' || /collection is inactive/i.test(error.message)
  );
}

// ─── Shared header ──────────────────────────────────────────────
interface CollectionHeaderProps {
  collection: Collection;
  total: number;
  right: React.ReactNode;
}

function CollectionHeader({ collection, total, right }: CollectionHeaderProps) {
  const navigate = useNavigate();
  const countForm = new Intl.PluralRules('ru').select(total);
  const documentUnit = countForm === 'one' ? 'документ' : countForm === 'few' ? 'документа' : 'документов';
  const itemCount = collection.collection_type === 'document'
    ? `${total.toLocaleString()} ${documentUnit}`
    : `${total.toLocaleString()} записей`;
  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <button
          className={styles.backBtn}
          onClick={() => navigate(`/gpt/collections${collection.tenant_id ? `?tenant_id=${encodeURIComponent(collection.tenant_id)}` : ''}`)}
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
            <span>{itemCount}</span>
          </div>
          {collection.capabilities?.can_edit_content !== true && (
            <div className={styles.permissionNotice} role="status">
              <Badge tone="neutral">Только просмотр</Badge>
              <span>
                Изменять содержимое могут администраторы и редакторы этой рабочей группы.
                {collection.capability_reasons?.can_edit_content
                  ? ` ${capabilityReasonCopy(collection.capability_reasons.can_edit_content, 'Изменять содержимое могут администраторы и редакторы этой рабочей группы.')}`
                  : ''}
              </span>
            </div>
          )}
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
  onPermissionDenied: CapabilityRefreshCallback;
}

function TableCollectionView({ collection, slug, onPermissionDenied }: TableViewProps) {
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
  const canEditContent = collection.capabilities?.can_edit_content === true;
  const canMutateRows = collection.capabilities?.mutate_rows === true;
  const canUploadCsv = collection.capabilities?.upload_csv === true;
  const tenantId = collection.tenant_id;
  const capabilityReason = (key: keyof CollectionCapabilities) =>
    capabilityReasonCopy(collection.capability_reasons?.[key], 'Операция временно недоступна.');

  React.useEffect(() => {
    if (searchQuery.trim() === debouncedSearch) return;
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, debouncedSearch]);

  const offset = (page - 1) * pageSize;
  const { data: dataResult, isLoading: dataLoading, isError: dataError, refetch } = useQuery({
    queryKey: qk.collections.data(slug, { limit: pageSize, offset, search: debouncedSearch || undefined, tenant_id: tenantId }),
    queryFn: () =>
      collectionsApi.getData(slug, {
        limit: pageSize,
        offset,
        search: debouncedSearch || undefined,
        tenant_id: tenantId,
      }),
    enabled: !!slug,
  });

  const rows = useMemo(() => dataResult?.items ?? [], [dataResult?.items]);
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
    mutationFn: (ids: string[]) => collectionsApi.deleteRows(slug, ids, tenantId),
    onSuccess: data => {
      showToast(`Удалено ${data.deleted} записей`, 'success');
      setSelectedIds(new Set<string>());
      queryClient.invalidateQueries({ queryKey: qk.collections.data(slug, { tenant_id: tenantId }) });
      queryClient.invalidateQueries({ queryKey: qk.collections.detail(slug, tenantId) });
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка удаления', 'error');
      if (err instanceof ApiError && err.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(err)) onPermissionDenied('unavailable');
    },
  });

  const handleSelectAll = useCallback(() => {
    setSelectedIds(allRowsSelected ? new Set<string>() : new Set(rowIds));
  }, [allRowsSelected, rowIds]);

  const handleSelectRow = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set<string>(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
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
      const result = await collectionsApi.uploadCSV(slug, uploadFile, { skip_errors: true, tenant_id: tenantId });
      showToast(`Загружено ${result.inserted_rows} записей`, 'success');
      if (result.errors.length > 0) {
        showToast(`${result.errors.length} записей пропущено из-за ошибок`, 'warning');
      }
      setUploadModalOpen(false);
      setUploadFile(null);
      refetch();
      queryClient.invalidateQueries({ queryKey: qk.collections.detail(slug, tenantId) });
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Ошибка загрузки', 'error');
      if (err instanceof ApiError && err.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(err)) onPermissionDenied('unavailable');
    } finally {
      setUploading(false);
    }
  };

  const handleDownloadTemplate = () => {
    window.open(collectionsApi.downloadTemplate(slug, tenantId), '_blank');
  };

  const pollExportReady = useCallback(async (exportId: string) => {
    const maxAttempts = 120;
    for (let i = 0; i < maxAttempts; i += 1) {
      const status = await collectionsApi.getCsvExportStatus(slug, exportId, tenantId);
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
  }, [slug, tenantId]);

  const handleExportCsv = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const started = await collectionsApi.startCsvExport(slug, tenantId);
      setActiveExportId(started.export_id);
      showToast('Экспорт запущен', 'success');
      await pollExportReady(started.export_id);
      showToast('CSV готов', 'success');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Ошибка экспорта CSV', 'error');
      if (err instanceof ApiError && err.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(err)) onPermissionDenied('unavailable');
    } finally {
      setExporting(false);
      setActiveExportId(null);
    }
  }, [exporting, pollExportReady, showToast, slug, tenantId, onPermissionDenied]);

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
      <Button variant="outline" onClick={handleDownloadTemplate}>
        <Icon name="download" size={16} />
        Шаблон CSV
      </Button>
      <Button variant="outline" onClick={handleExportCsv} disabled={exporting}>
        <Icon name="download" size={16} />
        {exporting ? (activeExportId ? 'Экспортируется...' : 'Запуск...') : 'Экспорт CSV'}
      </Button>
      {!isReadOnly && canEditContent && (
        <>
          <Button
            variant="danger"
            onClick={handleDeleteSelected}
            disabled={!canMutateRows || selectedIds.size === 0 || deleteMutation.isPending}
            title={!canMutateRows ? capabilityReason('mutate_rows') : undefined}
          >
            <Icon name="trash" size={16} />
            Удалить
          </Button>
          <Button onClick={() => setUploadModalOpen(true)} disabled={!canUploadCsv} title={!canUploadCsv ? capabilityReason('upload_csv') : undefined}>
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
        {dataError ? <CollectionLoadError onRetry={() => void refetch()} /> : dataLoading ? (
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
            {!debouncedSearch && !isReadOnly && canEditContent && (
              <Button onClick={() => setUploadModalOpen(true)} disabled={!canUploadCsv} title={!canUploadCsv ? capabilityReason('upload_csv') : undefined}>
                <Icon name="upload" size={16} />
                Загрузить CSV
              </Button>
            )}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                {!isReadOnly && canEditContent && (
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
                  <tr key={rowId} className={!isReadOnly && canEditContent && isSelected ? styles.selected : undefined}>
                    {!isReadOnly && canEditContent && (
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
            <button className={styles.paginationBtn} aria-label="Первая страница" onClick={() => setPage(1)} disabled={page === 1}>
              <Icon name="chevrons-left" size={16} />
            </button>
            <button className={styles.paginationBtn} aria-label="Предыдущая страница" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
              <Icon name="chevron-left" size={16} />
            </button>
            <span style={{ margin: '0 8px', fontSize: 13 }}>
              Страница {page} из {totalPages}
            </span>
            <button className={styles.paginationBtn} aria-label="Следующая страница" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              <Icon name="chevron-right" size={16} />
            </button>
            <button className={styles.paginationBtn} aria-label="Последняя страница" onClick={() => setPage(totalPages)} disabled={page === totalPages}>
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

      {uploadModalOpen && !isReadOnly && (
        <Modal
          open={uploadModalOpen}
          onClose={() => { setUploadModalOpen(false); setUploadFile(null); }}
          title="Загрузка CSV"
        >
          <div style={{ padding: 24 }}>
            {!canEditContent && <Alert variant="warning" title="Только просмотр" description="Право редактирования коллекции было отозвано. Файл сохранён; обновите права перед загрузкой." />}
            {canEditContent && !canUploadCsv && <Alert variant="warning" title="Загрузка временно недоступна" description={capabilityReason('upload_csv')} />}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              disabled={!canEditContent || !canUploadCsv || uploading}
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
                  <Button onClick={handleUpload} disabled={!canEditContent || !canUploadCsv || uploading} title={!canUploadCsv ? capabilityReason('upload_csv') : undefined}>
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
type DocSortKey = 'name' | 'created_at' | 'agg_status';
type DocSortDir = 'asc' | 'desc';

const PROCESSING_STATUSES = ['processing', 'queued', 'embedding', 'chunked', 'normalized'];

type StatusTone = 'success' | 'warn' | 'danger' | 'info' | 'neutral';

interface LongMemoryPresentation {
  label: string;
  tone: StatusTone;
  summary: string;
}

function metricValue(metrics: Record<string, unknown> | undefined, key: string): number | null {
  const value = metrics?.[key];
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value);
}

function getLongMemoryPresentation(
  memory: CollectionDocument['memory'] | undefined
): LongMemoryPresentation {
  if (!memory) {
    return {
      label: 'Не добавлена', tone: 'neutral', summary: '',
    };
  }

  const overall = memory.extraction_status.toLowerCase();
  const metrics = memory.extraction_metrics;
  const action = metrics.action;
  const steps = metrics.steps && typeof metrics.steps === 'object'
    ? metrics.steps as Record<string, unknown>
    : {};
  const extraction = steps.extract && typeof steps.extract === 'object'
    ? steps.extract as Record<string, unknown>
    : {};
  const indexing = steps.index && typeof steps.index === 'object'
    ? steps.index as Record<string, unknown>
    : {};
  const extractionDetails = extraction.metrics && typeof extraction.metrics === 'object'
    ? extraction.metrics as Record<string, unknown>
    : {};
  const extractState = String(extraction.status ?? '');
  const indexState = String(indexing.status ?? '');
  const extractFailed = extractState === 'failed';
  const indexFailed = indexState === 'failed';
  const extracting = ['running', 'processing'].includes(extractState);
  const indexingNow = ['running', 'processing'].includes(indexState);
  const stageQueued = ['queued', 'pending'].includes(extractState) || ['queued', 'pending'].includes(indexState);
  const extractionComplete = extractState === 'completed';
  const indexComplete = indexState === 'completed';

  let label = 'Не запускалась';
  let tone: StatusTone = 'neutral';
  if (action === 'delete' && ['queued', 'pending'].includes(overall)) {
    label = 'Удаление в очереди';
    tone = 'warn';
  } else if (action === 'delete' && ['running', 'processing'].includes(overall)) {
    label = 'Удаляется';
    tone = 'warn';
  } else if (action === 'delete' && overall === 'failed') {
    label = 'Ошибка удаления';
    tone = 'danger';
  } else if (overall === 'deleted') {
    label = 'Удалена';
  } else if (extractFailed) {
    label = 'Ошибка извлечения';
    tone = 'danger';
  } else if (indexFailed) {
    label = 'Ошибка индексации';
    tone = 'danger';
  } else if (extractionComplete && indexComplete) {
    label = 'Готова';
    tone = 'success';
  } else if (extracting || indexingNow || overall === 'running') {
    label = extracting && indexingNow
      ? 'Извлечение и индексация'
      : extracting ? 'Извлекается'
        : indexingNow ? 'Индексируется' : 'Обрабатывается';
    tone = 'warn';
  } else if (stageQueued || overall === 'queued' || overall === 'pending') {
    label = 'Ожидает обработки';
    tone = 'warn';
  } else if (overall === 'failed') {
    label = 'Ошибка';
    tone = 'danger';
  } else if (overall === 'cancelled') {
    label = 'Остановлена';
  } else if (overall === 'completed') {
    label = 'Готовность не подтверждена';
    tone = 'info';
  } else if (!memory.effective_enabled) {
    label = 'Не добавлена';
  }

  const extractionMetricParts: string[] = [];
  const facts = metricValue(extractionDetails, 'facts');
  const passages = metricValue(extractionDetails, 'passages');
  if (!extractFailed && !indexFailed && !stageQueued && !extracting && !indexingNow) {
    if (passages !== null) extractionMetricParts.push(`${formatCount(passages)} фрагм.`);
    else if (facts !== null) extractionMetricParts.push(`${formatCount(facts)} фактов`);
  }
  return {
    label,
    tone,
    summary: extractionMetricParts[0] ?? '',
  };
}

function formatDocumentSize(sizeBytes: number | null): string {
  if (sizeBytes === null || !Number.isFinite(sizeBytes) || sizeBytes < 0) return 'Размер не указан';
  if (sizeBytes < 1024) return `${formatCount(sizeBytes)} Б`;
  const units = ['КБ', 'МБ', 'ГБ', 'ТБ'];
  let value = sizeBytes / 1024;
  let unit = units[0];
  for (let index = 1; value >= 1024 && index < units.length; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)} ${unit}`;
}

function documentTypeLabel(document: CollectionDocument): string {
  const extension = document.filename.split('.').pop()?.trim().toUpperCase();
  return extension && extension !== document.filename.toUpperCase() ? extension : 'Файл';
}

interface DocumentViewProps {
  collection: Collection;
  onPermissionDenied: CapabilityRefreshCallback;
  permissionDenied: boolean;
}

function DocumentCollectionView({ collection, onPermissionDenied, permissionDenied }: DocumentViewProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const collectionSseRef = useRef<SSEClient | null>(null);
  const invalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const openModalDocIdRef = useRef<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortKey, setSortKey] = useState<DocSortKey>('created_at');
  const [sortDir, setSortDir] = useState<DocSortDir>('desc');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [statusModalDocId, setStatusModalDocId] = useState<string | null>(null);
  const [memoryActionPending, setMemoryActionPending] = useState<'add' | 'delete' | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadMetaFields, setUploadMetaFields] = useState<Record<string, string>>({});
  const [uploadMemoryPolicy, setUploadMemoryPolicy] = useState<'collection' | 'enabled' | 'disabled'>('collection');
  const [uploadScope, setUploadScope] = useState('company');
  const memoryScopesQuery = useQuery({
    queryKey: qk.memory.scopeCatalog(), queryFn: memoryScopesApi.list,
    staleTime: 30_000, gcTime: 5 * 60_000, retry: 1,
  });
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const collectionId = collection.id;
  const tenantId = collection.tenant_id;
  const capabilities = collection.capabilities;
  const canEditContent = capabilities?.can_edit_content === true;
  const canUploadDocuments = capabilities?.upload_documents === true;
  const canDeleteDocuments = capabilities?.delete_documents === true;
  const canIngest = capabilities?.ingest === true;
  const canManageMemory = capabilities?.manage_memory === true;
  const capabilityReason = (key: keyof CollectionCapabilities) =>
    capabilityReasonCopy(collection.capability_reasons?.[key], 'Операция временно недоступна.');

  useEffect(() => {
    if (searchQuery.trim() === debouncedSearchQuery) return;
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, debouncedSearchQuery]);

  const { data: uploadPolicy } = useQuery({
    queryKey: qk.collections.documentUploadPolicy(),
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

  const { data: docsData, isLoading: docsLoading, isError: docsError, refetch: refetchDocs } = useQuery({
    queryKey: qk.collections.documents(collectionId, { page, size: pageSize, query: debouncedSearchQuery, tenant_id: tenantId }),
    queryFn: () => {
      const params: NonNullable<Parameters<typeof collectionsApi.listDocuments>[1]> & { query?: string } = {
        page, size: pageSize,
        query: debouncedSearchQuery || undefined,
        tenant_id: tenantId,
      };
      return collectionsApi.listDocuments(collectionId, params);
    },
    refetchInterval: query => query.state.data?.items.some(doc =>
      ['pending', 'queued', 'running'].includes(doc.memory?.extraction_status ?? '')
    ) ? 5000 : false,
    enabled: !!collectionId,
  });

  const invalidateDocs = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: qk.collections.documentsRoot(collectionId) });
  }, [queryClient, collectionId, tenantId]);

  const debouncedInvalidateDocs = useCallback(() => {
    if (invalidateTimerRef.current) return;
    invalidateTimerRef.current = setTimeout(() => {
      invalidateTimerRef.current = null;
      void queryClient.invalidateQueries({ queryKey: qk.collections.documentsRoot(collectionId) });
    }, 500);
  }, [queryClient, collectionId, tenantId]);

  const documents = useMemo(() => docsData?.items ?? [], [docsData?.items]);
  const totalDocs = docsData?.total ?? 0;
  const totalDocumentPages = Math.max(1, Math.ceil(totalDocs / pageSize));
  useEffect(() => {
    if (docsData && page > totalDocumentPages) setPage(totalDocumentPages);
  }, [docsData, page, totalDocumentPages]);

  // Sort visible documents
  const filteredDocuments = useMemo(() => {
    let result = [...documents];

    result.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'name') cmp = (a.name || '').localeCompare(b.name || '');
      else if (sortKey === 'created_at') cmp = (a.created_at || '').localeCompare(b.created_at || '');
      else if (sortKey === 'agg_status') cmp = (a.agg_status || '').localeCompare(b.agg_status || '');
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [documents, sortKey, sortDir]);

  // Selection helpers
  const handleSort = (key: DocSortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('asc'); }
  };

  const handleSelectAll = () => {
    const allVisibleSelected = filteredDocuments.length > 0
      && filteredDocuments.every(document => selectedIds.has(document.id));
    setSelectedIds(
      allVisibleSelected ? new Set() : new Set(filteredDocuments.map(document => document.id))
    );
  };

  const handleSelect = (id: string) => {
    const s = new Set(selectedIds);
    if (s.has(id)) s.delete(id);
    else s.add(id);
    setSelectedIds(s);
  };

  // Selected docs computed
  const selectedDocs = useMemo(
    () => documents.filter(d => selectedIds.has(d.id)),
    [documents, selectedIds],
  );

  useEffect(() => {
    setSelectedIds(new Set());
  }, [page, pageSize, debouncedSearchQuery]);
  useEffect(() => {
    if (!canEditContent && !permissionDenied) setSelectedIds(new Set());
  }, [canEditContent, permissionDenied]);

  // Conditional bulk action visibility
  const ingestableDocuments = selectedDocs.filter(d =>
    ['uploaded', 'failed', 'partial'].includes(d.agg_status || 'uploaded')
  );
  const canBulkIngest = ingestableDocuments.length > 0;
  const canBulkDelete = selectedDocs.length > 0;

  useEffect(() => {
    if (!collectionId) return;
    const client = new SSEClient({
      url: collectionsApi.getStatusEventsUrl(collectionId, tenantId),
      onMessage: (events: SSEMessage[]) => {
        let needsInvalidate = false;

        for (const event of events) {
          const payload = event.data as Record<string, unknown> | null;

          // Snapshot repairs visible statuses; refetch also refreshes aggregate counters.
          if (event.type === 'rag.snapshot') {
            const items = (payload?.items as Array<Record<string, unknown>>) ?? [];
            if (items.length > 0) {
              queryClient.setQueriesData<CollectionDocumentsResponse>(
                { queryKey: qk.collections.documentsRoot(collectionId) },
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
            void queryClient.invalidateQueries({ queryKey: qk.collections.documentsRoot(collectionId) });
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
            void queryClient.invalidateQueries({ queryKey: qk.collections.documentStatus(openModalDocIdRef.current, tenantId) });
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
  }, [collectionId, tenantId, queryClient, debouncedInvalidateDocs]);

  // Drag & drop
  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!canEditContent || !canUploadDocuments) return;
    e.preventDefault(); setIsDragging(true);
  }, [canEditContent, canUploadDocuments]);
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (!canEditContent || !canUploadDocuments) return;
    e.preventDefault(); setIsDragging(false);
  }, [canEditContent, canUploadDocuments]);
  const handleDrop = useCallback((e: React.DragEvent) => {
    if (!canEditContent || !canUploadDocuments) return;
    e.preventDefault(); setIsDragging(false);
    const files = validateDocumentFiles(Array.from(e.dataTransfer.files));
    if (files.length > 0) {
      setUploadFiles(files);
      setUploadModalOpen(true);
    }
  }, [canEditContent, canUploadDocuments, validateDocumentFiles]);

  // Upload
  const handleUpload = async () => {
    if (!canEditContent || !canUploadDocuments) {
      setUploadError('Право редактирования недоступно. Файлы сохранены.');
      return;
    }
    if (uploadFiles.length === 0) return;
    const requiredMissing = userDefinedFields.find(
      field => field.required && (field.data_type === 'boolean'
        ? uploadMetaFields[field.name] === undefined
        : !String(uploadMetaFields[field.name] ?? '').trim()),
    );
    if (requiredMissing) {
      const message = `Заполните обязательное поле «${requiredMissing.description || requiredMissing.name}»`;
      setUploadError(message);
      showToast(message, 'error');
      return;
    }
    let typedMeta: Record<string, unknown>;
    try {
      typedMeta = {};
      for (const field of userDefinedFields) {
        const raw = uploadMetaFields[field.name];
        if (raw === undefined || raw.trim() === '') continue;
        if (field.data_type === 'boolean') typedMeta[field.name] = raw === 'true';
        else if (field.data_type === 'integer') {
          const value = Number(raw);
          if (!Number.isSafeInteger(value)) throw new Error(`Поле «${field.description || field.name}» должно быть целым числом`);
          typedMeta[field.name] = value;
        } else if (field.data_type === 'float') {
          const value = Number(raw);
          if (!Number.isFinite(value)) throw new Error(`Поле «${field.description || field.name}» должно быть числом`);
          typedMeta[field.name] = value;
        } else if (field.data_type === 'json') {
          typedMeta[field.name] = JSON.parse(raw);
        } else typedMeta[field.name] = raw;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Проверьте значения полей';
      setUploadError(message);
      showToast(message, 'error');
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const results = await Promise.allSettled(
        uploadFiles.map(file =>
          collectionsApi.uploadDocument(collectionId, {
            file,
            meta_fields: Object.keys(typedMeta).length > 0 ? typedMeta : undefined,
            auto_ingest: true,
            memory_enabled: uploadMemoryPolicy === 'collection' ? undefined : uploadMemoryPolicy === 'enabled',
            memory_scope_keys: [uploadScope],
          }, tenantId)
        )
      );
      const failedFiles = uploadFiles.filter((_, index) => results[index].status === 'rejected');
      const succeeded = results.length - failedFiles.length;
      const failed = failedFiles.length;
      if (succeeded > 0) showToast(`Загружено: ${succeeded} файлов`, 'success');
      if (failed > 0) {
        const failedNames = failedFiles.map(file => file.name).join(', ');
        const message = `Не удалось загрузить ${failed} файлов: ${failedNames}. Неудачные файлы оставлены в списке.`;
        setUploadError(message);
        showToast(`Ошибка загрузки: ${failed} файлов`, 'error');
        setUploadFiles(failedFiles);
        if (results.some(result => result.status === 'rejected' && result.reason instanceof ApiError && result.reason.status === 403)) {
          setUploadError('Право редактирования было отозвано. Выбранные файлы сохранены.');
          onPermissionDenied('forbidden');
        } else if (results.some(result => result.status === 'rejected' && isInactiveCollectionConflict(result.reason))) {
          setUploadError('Коллекция неактивна. Выбранные файлы сохранены.');
          onPermissionDenied('unavailable');
        }
      } else {
        setUploadModalOpen(false);
        setUploadFiles([]);
        setUploadMetaFields({});
        setUploadMemoryPolicy('collection');
        setUploadError(null);
      }
      if (succeeded > 0) invalidateDocs();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Ошибка загрузки';
      setUploadError(message);
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
      await collectionsApi.deleteDocuments(collectionId, Array.from(selectedIds), tenantId);
      showToast(`Удалено: ${selectedIds.size} документов`, 'success');
      setSelectedIds(new Set());
      invalidateDocs();
    } catch (error) {
      showToast('Ошибка удаления', 'error');
      if (error instanceof ApiError && error.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(error)) onPermissionDenied('unavailable');
    }
  };

  const handleBulkMemoryAction = async (action: 'add' | 'delete') => {
    if (selectedIds.size === 0 || memoryActionPending !== null) return;
    const documentIds = Array.from(selectedIds);
    setMemoryActionPending(action);
    try {
      const results = await Promise.allSettled(documentIds.map(id => action === 'add'
        ? collectionsApi.addDocumentToMemory(collectionId, id, tenantId)
        : collectionsApi.removeDocumentFromMemory(collectionId, id, tenantId)));
      const succeeded = results.filter(result => result.status === 'fulfilled').length;
      const failedIds = documentIds.filter((_, index) => results[index]?.status === 'rejected');
      const failed = failedIds.length;
      if (results.some(result => result.status === 'rejected' && result.reason instanceof ApiError && result.reason.status === 403)) {
        onPermissionDenied('forbidden');
      } else if (results.some(result => result.status === 'rejected' && isInactiveCollectionConflict(result.reason))) {
        onPermissionDenied('unavailable');
      }
      const operationLabel = action === 'add' ? 'Добавление в LongMemory' : 'Удаление из LongMemory';
      showToast(failed === 0
        ? `${operationLabel} поставлено в очередь: ${succeeded}`
        : `LongMemory: поставлено в очередь ${succeeded}, ошибок ${failed}`, failed === 0 ? 'success' : 'error');
      setSelectedIds(new Set(failedIds));
      if (succeeded > 0) invalidateDocs();
    } catch (error) {
      showToast('Не удалось выполнить действие LongMemory', 'error');
      if (error instanceof ApiError && error.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(error)) onPermissionDenied('unavailable');
    } finally {
      setMemoryActionPending(null);
    }
  };

  const handleBulkIngest = async () => {
    if (ingestableDocuments.length === 0) return;
    try {
      const results = await Promise.allSettled(
        ingestableDocuments.map(document => collectionsApi.startDocIngest(collectionId, document.id, tenantId))
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
        if (error instanceof ApiError && error.status === 403) onPermissionDenied('forbidden');
        if (isInactiveCollectionConflict(error)) {
          onPermissionDenied('unavailable');
          failed += 1;
          return;
        }
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

  // Status badge
  const getStatusBadge = (status: string) => {
    const map: Record<string, { tone: 'success' | 'warn' | 'danger' | 'info' | 'neutral'; label: string }> = {
      ready: { tone: 'success', label: 'Готов' },
      processing: { tone: 'warn', label: 'Обработка' },
      queued: { tone: 'warn', label: 'В очереди' },
      embedding: { tone: 'warn', label: 'Эмбеддинг' },
      chunked: { tone: 'info', label: 'Разбит' },
      normalized: { tone: 'info', label: 'Нормализован' },
      failed: { tone: 'danger', label: 'Ошибка' },
      partial: { tone: 'warn', label: 'Частично готов' },
      archived: { tone: 'neutral', label: 'В архиве' },
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

  const headerRight = canEditContent ? (
    <Button
      variant="primary"
      onClick={() => setUploadModalOpen(true)}
      disabled={!canUploadDocuments}
      title={!canUploadDocuments ? capabilityReason('upload_documents') : undefined}
    >
      <Icon name="upload" size={16} />
      Загрузить документы
    </Button>
  ) : null;

  return (
    <>
      <CollectionHeader collection={collection} total={totalDocs} right={headerRight} />

      {/* Toolbar */}
      <div className={styles.docToolbar}>
        <div className={styles.docToolbarLeft}>
          <label className={styles.srOnly} htmlFor="document-search">Поиск по документам</label>
          <Input
            id="document-search"
            className={styles.search}
            placeholder="Поиск по имени или тегам..."
            value={searchQuery}
            disabled={memoryActionPending !== null}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
        <div className={styles.docToolbarRight}>
      {selectedIds.size > 0 && canEditContent && (
            <div className={styles.docBulkActions}>
              <span className={styles.docSelectedCount}>Выбрано {selectedIds.size}</span>
              {canBulkIngest && (
                <Button variant="ghost" size="sm" disabled={!canIngest || memoryActionPending !== null} title={!canIngest ? capabilityReason('ingest') : undefined} onClick={handleBulkIngest}>
                  Запустить обработку
                </Button>
              )}
              <Button variant="outline" size="sm" disabled={!canManageMemory || memoryActionPending !== null} title={!canManageMemory ? capabilityReason('manage_memory') : undefined} loading={memoryActionPending === 'add'} onClick={() => { void handleBulkMemoryAction('add'); }}>
                Добавить в LongMemory
              </Button>
              <Button variant="outline" size="sm" className={styles.dangerAction} disabled={!canManageMemory || memoryActionPending !== null} title={!canManageMemory ? capabilityReason('manage_memory') : undefined} loading={memoryActionPending === 'delete'} onClick={() => { void handleBulkMemoryAction('delete'); }}>
                Удалить из LongMemory
              </Button>
              {canBulkDelete && (
                <Button variant="outline" size="sm" className={styles.dangerAction} disabled={!canDeleteDocuments || memoryActionPending !== null} title={!canDeleteDocuments ? capabilityReason('delete_documents') : undefined} onClick={handleBulkDelete}>
                  Удалить документы
                </Button>
              )}
              <Button variant="ghost" size="sm" disabled={memoryActionPending !== null} onClick={() => setSelectedIds(new Set())}>
                Снять выбор
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Document table */}
      <div
        className={`${styles.tableContainer} ${isDragging ? styles.dragging : ''}`}
        onDragOver={canEditContent && canUploadDocuments ? handleDragOver : undefined}
        onDragLeave={canEditContent && canUploadDocuments ? handleDragLeave : undefined}
        onDrop={canEditContent && canUploadDocuments ? handleDrop : undefined}
      >
        {isDragging && canEditContent && canUploadDocuments && (
          <div className={styles.dropOverlay}>
            <div className={styles.dropContent}>
              <Icon name="upload" size={48} />
              <span>Перетащите файлы для загрузки</span>
            </div>
          </div>
        )}

        {docsError ? <CollectionLoadError onRetry={() => void refetchDocs()} /> : docsLoading ? (
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
              {searchQuery
                ? 'Попробуйте изменить запрос'
                : 'Загрузите первый документ для начала работы'}
            </p>
            {!searchQuery && canEditContent && (
              <Button onClick={() => setUploadModalOpen(true)} disabled={!canUploadDocuments} title={!canUploadDocuments ? capabilityReason('upload_documents') : undefined}>Загрузить документ</Button>
            )}
          </div>
        ) : (
          <table className={`${styles.docTable} ${styles.documentTable}`}>
            <colgroup>
              <col className={styles.documentSelectColumn} />
              <col className={styles.documentNameColumn} />
              <col className={styles.ragStatusColumn} />
              <col className={styles.memoryStatusColumn} />
              <col className={styles.projectColumn} />
              {metaFields.map(field => <col key={field.name} className={styles.metadataColumn} />)}
              <col className={styles.createdColumn} />
            </colgroup>
            <thead>
              <tr>
                {canEditContent && <th className={styles.checkboxCell}>
                  <input
                    type="checkbox"
                    checked={filteredDocuments.length > 0 && filteredDocuments.every(document => selectedIds.has(document.id))}
                    disabled={memoryActionPending !== null}
                    onChange={handleSelectAll}
                    aria-label="Выбрать все документы на странице"
                  />
                </th>}
                <th scope="col" className={styles.sortable} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className={styles.sortHeader} onClick={() => handleSort('name')}>
                    Документ
                    {sortKey === 'name' && <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />}
                  </button>
                </th>
                <th scope="col" className={styles.sortable} aria-sort={sortKey === 'agg_status' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className={styles.sortHeader} onClick={() => handleSort('agg_status')}>
                    RAG
                    {sortKey === 'agg_status' && <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />}
                  </button>
                </th>
                <th scope="col">LongMemory</th>
                <th scope="col">Проект памяти</th>
                {metaFields.map(f => (
                  <th scope="col" key={f.name} title={f.label}>{f.label}</th>
                ))}
                <th scope="col" className={styles.sortable} aria-sort={sortKey === 'created_at' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className={styles.sortHeader} onClick={() => handleSort('created_at')}>
                    Добавлен
                    {sortKey === 'created_at' && <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={14} />}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map(doc => {
                const memoryView = getLongMemoryPresentation(doc.memory);
                const projectKeys = doc.memory?.scope_keys?.length
                  ? doc.memory.scope_keys
                  : doc.memory?.project_keys ?? [];
                const projectNames = projectKeys.map(key =>
                  memoryScopesQuery.data?.find(scope => scope.key === key)?.name ?? key
                );
                const chunkCount = doc.artifacts?.chunks?.chunk_count;
                return (
                  <tr key={doc.id} className={selectedIds.has(doc.id) ? styles.selected : ''}>
                    {canEditContent && <td className={styles.checkboxCell}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(doc.id)}
                        disabled={memoryActionPending !== null}
                        onChange={() => handleSelect(doc.id)}
                        aria-label={`Выбрать документ ${doc.name || doc.filename}`}
                      />
                    </td>}
                    <td className={styles.nameCell}>
                      <div className={styles.documentNameRow}>
                        <button
                          className={styles.nameButton}
                          onClick={() => { openModalDocIdRef.current = doc.id; setStatusModalDocId(doc.id); }}
                          title={doc.name || doc.filename}
                        >
                          {doc.name || 'Без имени'}
                        </button>
                      </div>
                      <span className={styles.documentSubline}>
                        {documentTypeLabel(doc)} · {formatDocumentSize(doc.size_bytes)}
                      </span>
                    </td>
                    <td className={styles.statusCell}>
                      <button
                        className={styles.statusButton}
                        onClick={() => { openModalDocIdRef.current = doc.id; setStatusModalDocId(doc.id); }}
                        aria-label={`Статус RAG для ${doc.name || doc.filename}: ${doc.agg_status || 'загружен'}`}
                      >
                        {getStatusBadge(doc.agg_status || 'uploaded')}
                      </button>
                      <span
                        className={styles.metricLine}
                        title={typeof chunkCount === 'number' ? `${formatCount(chunkCount)} чанков RAG` : 'Число чанков пока недоступно'}
                      >
                        {typeof chunkCount === 'number' ? `${formatCount(chunkCount)} чанков` : 'Чанки: нет данных'}
                      </span>
                    </td>
                    <td className={styles.longMemoryCell}>
                      <button
                        type="button"
                        className={styles.memoryStatusButton}
                        onClick={() => { openModalDocIdRef.current = doc.id; setStatusModalDocId(doc.id); }}
                        aria-label={`Статус LongMemory для ${doc.name || doc.filename}: ${memoryView.label}`}
                      >
                        <Badge tone={memoryView.tone} size="small">{memoryView.label}</Badge>
                      </button>
                      {memoryView.summary && <span className={styles.memorySummary}>{memoryView.summary}</span>}
                    </td>
                    <td className={styles.projectCell}>
                      {projectNames.length > 0 ? (
                        <div className={styles.projectList}>
                          {projectNames.map((name, index) => (
                            <Badge key={`${projectKeys[index]}-${index}`} tone="info" size="small" title={projectKeys[index]}>
                              {name}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className={styles.muted}>Не указано</span>
                      )}
                    </td>
                    {metaFields.map(f => (
                      <td key={f.name} className={`${styles.muted} ${styles.metadataCell}`} title={renderMetaField(doc.meta_fields?.[f.name])}>
                        {renderMetaField(doc.meta_fields?.[f.name])}
                      </td>
                    ))}
                    <td className={styles.muted}>{formatDate(doc.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {totalDocs > 0 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>Показано {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalDocs)} из {totalDocs.toLocaleString()}</div>
          <div className={styles.paginationControls}>
            <button className={styles.paginationBtn} aria-label="Первая страница" onClick={() => setPage(1)} disabled={page === 1 || memoryActionPending !== null}><Icon name="chevrons-left" size={16} /></button>
            <button className={styles.paginationBtn} aria-label="Предыдущая страница" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page === 1 || memoryActionPending !== null}><Icon name="chevron-left" size={16} /></button>
            <span style={{ margin: '0 8px', fontSize: 13 }}>Страница {page} из {totalDocumentPages}</span>
            <button className={styles.paginationBtn} aria-label="Следующая страница" onClick={() => setPage((value) => Math.min(totalDocumentPages, value + 1))} disabled={page >= totalDocumentPages || memoryActionPending !== null}><Icon name="chevron-right" size={16} /></button>
            <button className={styles.paginationBtn} aria-label="Последняя страница" onClick={() => setPage(totalDocumentPages)} disabled={page >= totalDocumentPages || memoryActionPending !== null}><Icon name="chevrons-right" size={16} /></button>
          </div>
          <div className={styles.pageSize}><span>Показывать:</span><select value={pageSize} disabled={memoryActionPending !== null} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></div>
        </div>
      )}

      {/* Upload modal */}
      <Modal
        open={uploadModalOpen}
        onClose={() => { setUploadModalOpen(false); setUploadFiles([]); setUploadMetaFields({}); setUploadMemoryPolicy('collection'); setUploadError(null); }}
        title="Загрузка документов"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadModalOpen(false)}>Отмена</Button>
            <Button onClick={handleUpload} disabled={!canEditContent || !canUploadDocuments || uploadFiles.length === 0 || uploading || !memoryScopesQuery.data?.some(scope => scope.key === uploadScope)} title={!canUploadDocuments ? capabilityReason('upload_documents') : undefined}>
              {uploading ? 'Загрузка...' : `Загрузить (${uploadFiles.length})`}
            </Button>
          </>
        }
      >
        <div className={styles.docUploadContent}>
          {!canEditContent && <Alert variant="warning" title="Только просмотр" description="Право редактирования было отозвано. Файлы и заполненные поля сохранены; обновите права перед загрузкой." />}
          {canEditContent && !canUploadDocuments && <Alert variant="warning" title="Загрузка временно недоступна" description={capabilityReason('upload_documents')} />}
          <div
            className={styles.dropZone}
            onClick={(e) => { e.stopPropagation(); if (canEditContent && canUploadDocuments) fileInputRef.current?.click(); }}
            role="button"
            tabIndex={canEditContent && canUploadDocuments ? 0 : -1}
            aria-disabled={!canEditContent || !canUploadDocuments}
            onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && canEditContent && canUploadDocuments) { e.preventDefault(); fileInputRef.current?.click(); } }}
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
            disabled={!canEditContent || !canUploadDocuments || uploading}
            style={{ display: 'none' }}
            onChange={e => {
              const files = validateDocumentFiles(Array.from(e.target.files || []));
              if (files.length > 0) {
                setUploadFiles(prev => [...prev, ...files]);
              }
              if (e.target) e.target.value = '';
            }}
          />
          <label className={styles.uploadField}>
            <span>Проект для LongMemory</span>
            <Select value={uploadScope} onChange={setUploadScope}
              disabled={uploading || memoryScopesQuery.isLoading || memoryScopesQuery.isError}
              options={(memoryScopesQuery.data ?? []).map(scope => ({ value: scope.key, label: `${scope.name} (${scope.key})` }))} />
            {memoryScopesQuery.isError && <span role="alert">Не удалось загрузить проекты памяти.</span>}
          </label>
          <label className={styles.uploadField}>
            <span>LongMemory</span>
            <select
              value={uploadMemoryPolicy}
              onChange={(event) => setUploadMemoryPolicy(event.target.value as 'collection' | 'enabled' | 'disabled')}
            >
              <option value="collection">Наследовать настройку коллекции</option>
              <option value="enabled">Включить для этих документов</option>
              <option value="disabled">Исключить из LongMemory</option>
            </select>
          </label>
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
          sseUrl={collectionsApi.getDocumentStatusEventsUrl(collectionId, statusModalDocId, tenantId)}
          statusGraphUrl={`/collections/${collectionId}/docs/${statusModalDocId}/status-graph${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`}
          downloadUrlPrefix={`/collections/${collectionId}/docs/${statusModalDocId}/download`}
          retryUrlPrefix={`/collections/${collectionId}/docs/${statusModalDocId}/ingest/retry`}
          memoryUrl={`/collections/${collectionId}/docs/${statusModalDocId}/memory${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`}
          stopUrlPrefix={`/collections/${collectionId}/docs/${statusModalDocId}/ingest/stop`}
          tenantId={tenantId}
          collectionCapabilities={capabilities}
          capabilityReasons={collection.capability_reasons}
          onPermissionDenied={onPermissionDenied}
        />
      )}
    </>
  );
}

// ─── Template collection view ───────────────────────────────────
interface TemplateViewProps {
  collection: Collection;
  slug: string;
  onPermissionDenied: CapabilityRefreshCallback;
  permissionDenied: boolean;
}

function TemplateCollectionView({ collection, slug, onPermissionDenied, permissionDenied }: TemplateViewProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [statusModalRow, setStatusModalRow] = useState<CollectionTemplate | null>(null);
  const [actionsMenu, setActionsMenu] = useState<{ row: CollectionTemplate; anchorEl: HTMLElement } | null>(null);

  const collectionId = collection.id;
  const tenantId = collection.tenant_id;
  const capabilities = collection.capabilities;
  const canEditContent = capabilities?.can_edit_content === true;
  const canUploadTemplates = capabilities?.upload_templates === true;
  const canAnalyzeTemplates = capabilities?.analyze_templates === true;
  const canDeleteTemplates = capabilities?.delete_templates === true;
  const capabilityReason = (key: keyof CollectionCapabilities) =>
    capabilityReasonCopy(collection.capability_reasons?.[key], 'Операция временно недоступна.');

  useEffect(() => {
    if (searchQuery.trim() === debouncedSearchQuery) return;
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, debouncedSearchQuery]);

  const templateQueryKey = useMemo(() => qk.collections.templates(collectionId, { page, size: pageSize, query: debouncedSearchQuery, tenant_id: tenantId }), [collectionId, page, pageSize, debouncedSearchQuery, tenantId]);

  const { data: templatesData, isLoading: templatesLoading, isError: templatesError, refetch: refetchTemplates } = useQuery({
    queryKey: templateQueryKey,
    queryFn: () => collectionsApi.listTemplates(collectionId, { page, size: pageSize, query: debouncedSearchQuery || undefined, tenant_id: tenantId }),
    enabled: !!collectionId,
    refetchInterval: 10000,
  });

  const templates = templatesData?.items ?? [];
  const totalTemplates = templatesData?.total ?? 0;

  const filteredTemplates = templates;
  const totalPages = Math.max(1, Math.ceil(totalTemplates / pageSize));
  useEffect(() => {
    if (templatesData && page > totalPages) setPage(totalPages);
  }, [templatesData, page, totalPages]);
  useEffect(() => {
    if (!canEditContent && !permissionDenied) setSelectedIds(new Set<string>());
  }, [canEditContent, permissionDenied]);

  const invalidateTemplates = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: qk.collections.templatesRoot(collectionId) });
    void queryClient.invalidateQueries({ queryKey: qk.collections.detail(slug, tenantId) });
  }, [collectionId, queryClient, slug, tenantId]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => collectionsApi.uploadTemplate(collectionId, { file }, tenantId),
    onSuccess: () => {
      showToast('Шаблон загружен, анализ запущен', 'success');
      setUploadFile(null);
      setUploadModalOpen(false);
      invalidateTemplates();
    },
    onError: (err: Error) => {
      showToast(err.message || 'Ошибка загрузки шаблона', 'error');
      if (err instanceof ApiError && err.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(err)) onPermissionDenied('unavailable');
    },
    onSettled: () => {
      setUploading(false);
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: (rowIds: string[]) => collectionsApi.analyzeTemplates(collectionId, rowIds, tenantId),
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
      if (err instanceof ApiError && err.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(err)) onPermissionDenied('unavailable');
    },
  });

  useEffect(() => {
    if (!collectionId) return;
    const client = new SSEClient({
      url: collectionsApi.getTemplateCollectionStatusEventsUrl(collectionId, tenantId),
      onMessage: (events: SSEMessage[]) => {
        for (const event of events) {
          const payload = event.data as Record<string, unknown> | null;
          if (!payload) continue;

          if (event.type === 'rag.snapshot') {
            void queryClient.invalidateQueries({ queryKey: qk.collections.templatesRoot(collectionId) });
            continue;
          }

          const item = payload.item as CollectionTemplate | undefined;
          if (!item?.id) continue;
          void queryClient.invalidateQueries({ queryKey: qk.collections.templatesRoot(collectionId) });
        }
      },
    });
    void client.connect();
    return () => {
      client.disconnect();
    };
  }, [collectionId, tenantId, queryClient, templateQueryKey]);

  const handleSelectAll = useCallback(() => {
    const visibleIds = filteredTemplates.map((item) => item.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set<string>() : new Set<string>(visibleIds));
  }, [filteredTemplates, selectedIds]);

  const handleSelectRow = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleUpload = useCallback(() => {
    if (!canEditContent || !canUploadTemplates) return;
    if (!uploadFile) return;
    setUploading(true);
    uploadMutation.mutate(uploadFile);
  }, [canEditContent, canUploadTemplates, uploadFile, uploadMutation]);

  const handleDeleteRows = useCallback(async (ids: string[]) => {
    if (!canEditContent || !canDeleteTemplates || ids.length === 0) return;
    try {
      await collectionsApi.deleteTemplates(collectionId, ids, tenantId);
      showToast(`Удалено: ${ids.length} шаблонов`, 'success');
      setSelectedIds(new Set<string>());
      invalidateTemplates();
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Ошибка удаления шаблонов', 'error');
      if (error instanceof ApiError && error.status === 403) onPermissionDenied('forbidden');
      else if (isInactiveCollectionConflict(error)) onPermissionDenied('unavailable');
    }
  }, [canEditContent, canDeleteTemplates, collectionId, tenantId, invalidateTemplates, onPermissionDenied, showToast]);

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
    if (!canEditContent || !canAnalyzeTemplates) return;
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    analyzeMutation.mutate(ids);
  }, [canEditContent, canAnalyzeTemplates, analyzeMutation, selectedIds]);

  const handleAnalyzeOne = useCallback((rowId: string) => {
    if (!canEditContent || !canAnalyzeTemplates) return;
    analyzeMutation.mutate([rowId]);
  }, [canEditContent, canAnalyzeTemplates, analyzeMutation]);

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

  const openStatusModal = useCallback((row: CollectionTemplate) => {
    setStatusModalRow(row);
  }, []);

  const openActionsMenu = useCallback((row: CollectionTemplate, anchorEl: HTMLElement) => {
    setActionsMenu({ row, anchorEl });
  }, []);

  const closeActionsMenu = useCallback(() => {
    setActionsMenu(null);
  }, []);

  const handleDownload = useCallback(async (row: CollectionTemplate) => {
    try {
      const { download_url } = await collectionsApi.getTemplateDownload(collectionId, row.id, tenantId);
      window.open(download_url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Оригинальный файл не найден', 'warning');
    }
  }, [collectionId, tenantId, showToast]);

  const getTemplateStatusBadge = (row: CollectionTemplate) => {
    const status = String(row.runtime_status ?? row.status ?? 'uploaded').toLowerCase();
    const map: Record<string, { tone: 'success' | 'warn' | 'neutral' | 'info' | 'danger'; label: string }> = {
      uploaded: { tone: 'neutral', label: 'Загружен' },
      processing: { tone: 'warn', label: 'Обработка' },
      approval_required: { tone: 'info', label: 'Утверждение' },
      ready: { tone: 'success', label: 'Готов' },
      failed: { tone: 'danger', label: 'Ошибка' },
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
      {canEditContent && selectedIds.size > 0 && (
        <Button variant="danger" onClick={handleDeleteSelected} disabled={!canDeleteTemplates} title={!canDeleteTemplates ? capabilityReason('delete_templates') : undefined}>
          <Icon name="trash" size={16} />
          Удалить
        </Button>
      )}
      {canEditContent && selectedIds.size > 0 && (
        <Button variant="ghost" onClick={handleAnalyzeSelected} disabled={!canAnalyzeTemplates || analyzeMutation.isPending} title={!canAnalyzeTemplates ? capabilityReason('analyze_templates') : undefined}>
          <Icon name="sparkles" size={16} />
          {analyzeMutation.isPending ? 'Анализ...' : 'Запустить анализ'}
        </Button>
      )}
      {canEditContent && (
        <Button variant="primary" onClick={() => setUploadModalOpen(true)} disabled={!canUploadTemplates} title={!canUploadTemplates ? capabilityReason('upload_templates') : undefined}>
          <Icon name="upload" size={16} />
          Загрузить шаблон
        </Button>
      )}
    </>
  );

  const visibleIds = filteredTemplates.map((item) => item.id);
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  return (
    <>
      <CollectionHeader collection={collection} total={totalTemplates} right={headerRight} />

      <div className={styles.tableContainer}>
        {templatesError ? <CollectionLoadError onRetry={() => void refetchTemplates()} /> : templatesLoading ? (
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
            {!searchQuery && canEditContent && (
              <Button onClick={() => setUploadModalOpen(true)} disabled={!canUploadTemplates} title={!canUploadTemplates ? capabilityReason('upload_templates') : undefined}>
                <Icon name="upload" size={16} />
                Загрузить шаблон
              </Button>
            )}
          </div>
        ) : (
          <table className={styles.docTable}>
            <thead>
              <tr>
                {canEditContent && <th className={styles.checkboxCell}>
                  <input type="checkbox" checked={allSelected} onChange={handleSelectAll} />
                </th>}
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
                    {canEditContent && <td className={styles.checkboxCell}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(row.id)}
                        onChange={() => handleSelectRow(row.id)}
                      />
                    </td>}
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
                        {row.has_error && row.error_message ? (
                          <span style={{ color: 'var(--color-danger-600, #c62828)', fontSize: 12 }}>{row.error_message}</span>
                        ) : null}
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

      {totalTemplates > 0 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>Показано {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalTemplates)} из {totalTemplates.toLocaleString()}</div>
          <div className={styles.paginationControls}>
            <button className={styles.paginationBtn} aria-label="Первая страница" onClick={() => setPage(1)} disabled={page === 1}><Icon name="chevrons-left" size={16} /></button>
            <button className={styles.paginationBtn} aria-label="Предыдущая страница" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page === 1}><Icon name="chevron-left" size={16} /></button>
            <span style={{ margin: '0 8px', fontSize: 13 }}>Страница {page} из {totalPages}</span>
            <button className={styles.paginationBtn} aria-label="Следующая страница" onClick={() => setPage((value) => Math.min(totalPages, value + 1))} disabled={page === totalPages}><Icon name="chevron-right" size={16} /></button>
            <button className={styles.paginationBtn} aria-label="Последняя страница" onClick={() => setPage(totalPages)} disabled={page === totalPages}><Icon name="chevrons-right" size={16} /></button>
          </div>
          <div className={styles.pageSize}><span>Показывать:</span><select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></div>
        </div>
      )}

      <Modal
        open={uploadModalOpen}
        onClose={() => { setUploadModalOpen(false); setUploadFile(null); }}
        title="Загрузка шаблона"
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadModalOpen(false)}>Отмена</Button>
            <Button onClick={handleUpload} disabled={!canEditContent || !canUploadTemplates || !uploadFile || uploading} title={!canUploadTemplates ? capabilityReason('upload_templates') : undefined}>
              {uploading ? 'Загрузка...' : 'Загрузить'}
            </Button>
          </>
        }
      >
        <div className={styles.docUploadContent}>
          {!canEditContent && <Alert variant="warning" title="Только просмотр" description="Право редактирования было отозвано. Файл сохранён; обновите права перед загрузкой." />}
          {canEditContent && !canUploadTemplates && <Alert variant="warning" title="Загрузка временно недоступна" description={capabilityReason('upload_templates')} />}
          <div
            className={styles.dropZone}
            onClick={(e) => { e.stopPropagation(); if (canEditContent && canUploadTemplates) fileInputRef.current?.click(); }}
            role="button"
            tabIndex={canEditContent && canUploadTemplates ? 0 : -1}
            aria-disabled={!canEditContent || !canUploadTemplates}
            onKeyDown={(e) => {
              if ((e.key === 'Enter' || e.key === ' ') && canEditContent && canUploadTemplates) {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
          >
            <Icon name="upload" size={32} />
            <span>Нажмите, чтобы выбрать файл шаблона</span>
            <span className={styles.dropZoneHint}>Поддерживаются Excel-шаблоны XLSX и XLSM</span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm"
            disabled={!canEditContent || !canUploadTemplates || uploading}
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

      <DropdownMenu
        isOpen={Boolean(actionsMenu?.row)}
        onClose={closeActionsMenu}
        anchorEl={actionsMenu?.anchorEl ?? null}
        items={actionsMenu?.row ? [
          {
            label: 'Скачать',
            onClick: () => handleDownload(actionsMenu.row),
            disabled: false,
          },
          ...(canEditContent ? [{
            label: 'Анализ',
            onClick: () => handleAnalyzeOne(actionsMenu.row.id),
            disabled: !canAnalyzeTemplates || analyzeMutation.isPending,
            title: !canAnalyzeTemplates ? capabilityReason('analyze_templates') : undefined,
          }] : []),
          ...(canEditContent ? [{
            label: 'Удалить',
            onClick: () => handleDeleteOne(actionsMenu.row.id, actionsMenu.row.title || 'Шаблон'),
            variant: 'danger',
            disabled: !canDeleteTemplates,
            title: !canDeleteTemplates ? capabilityReason('delete_templates') : undefined,
          } as const] : []),
        ] : []}
      />

      {statusModalRow && (
        <TemplateStatusModal
          collectionId={collectionId}
          tenantId={tenantId}
          collection={collection}
          onPermissionDenied={onPermissionDenied}
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
  const [searchParams] = useSearchParams();
  const tenantId = searchParams.get('tenant_id') || undefined;
  const [capabilityRefreshReason, setCapabilityRefreshReason] = useState<CapabilityRefreshReason | null>(null);

  const { data: collection, isLoading: collectionLoading, error: collectionError, refetch: refetchCollection } = useQuery({
    queryKey: qk.collections.detail(slug || '', tenantId),
    queryFn: () => collectionsApi.getBySlug(slug!, tenantId),
    enabled: !!slug && slug !== 'glossary',
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  useEffect(() => {
    setCapabilityRefreshReason(null);
  }, [slug, tenantId]);
  const handlePermissionDenied = useCallback(async (reason: CapabilityRefreshReason = 'forbidden'): Promise<Collection | null> => {
    setCapabilityRefreshReason(reason);
    try {
      const result = await refetchCollection();
      const freshCollection = result.isSuccess ? result.data ?? null : null;
      if (reason === 'forbidden') {
        if (freshCollection?.capabilities?.can_edit_content === true) {
          setCapabilityRefreshReason(null);
        }
      } else if (freshCollection?.capabilities) {
        setCapabilityRefreshReason(null);
      }
      return freshCollection;
    } catch {
      return null;
    }
  }, [refetchCollection]);

  if (slug === 'glossary') {
    return <GlossaryCollectionView />;
  }

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
    if (collectionError && !(collectionError instanceof ApiError && collectionError.status === 404)) {
      return <CollectionLoadError onRetry={() => void refetchCollection()} />;
    }
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
  const isExternal = collection.collection_type === 'api' || collection.collection_type === 'sql';
  const renderedCollection: Collection = capabilityRefreshReason
    ? {
        ...collection,
        capabilities: {
          ...collection.capabilities,
          view_content: collection.capabilities?.view_content ?? false,
          view_schema: collection.capabilities?.view_schema ?? false,
          download: collection.capabilities?.download ?? false,
          can_edit_content: false,
          upload_documents: false,
          delete_documents: false,
          ingest: false,
          manage_memory: false,
          upload_csv: false,
          mutate_rows: false,
          reindex: false,
          upload_templates: false,
          analyze_templates: false,
          approve_templates: false,
          edit_templates: false,
          delete_templates: false,
        },
      }
    : collection;

  return (
    <div className={styles.page}>
      {capabilityRefreshReason && (
        <Alert
          variant="warning"
          title={capabilityRefreshReason === 'forbidden' ? 'Права изменились' : 'Действие временно недоступно'}
          description={capabilityRefreshReason === 'forbidden'
            ? 'Сервер отклонил изменение. Файлы, черновики и выбор сохранены; действия отключены до подтверждения права редактирования.'
            : 'Коллекция временно недоступна для этого действия. Файлы, черновики и выбор сохранены; проверяем актуальные возможности.'}
        />
      )}
      {isExternal ? (
        <ExternalCollectionOverview key={collection.id} collection={renderedCollection} />
      ) : isDocument ? (
        <DocumentCollectionView key={collection.id} collection={renderedCollection} onPermissionDenied={() => { void handlePermissionDenied('forbidden'); }} permissionDenied={capabilityRefreshReason !== null} />
      ) : isTemplate ? (
        <TemplateCollectionView key={collection.id} collection={renderedCollection} slug={slug!} onPermissionDenied={handlePermissionDenied} permissionDenied={capabilityRefreshReason !== null} />
      ) : (
        <TableCollectionView key={collection.id} collection={renderedCollection} slug={slug!} onPermissionDenied={() => { void handlePermissionDenied('forbidden'); }} />
      )}
    </div>
  );
}

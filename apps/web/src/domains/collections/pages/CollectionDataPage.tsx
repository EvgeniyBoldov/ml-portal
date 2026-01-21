/**
 * CollectionDataPage - View and manage collection data
 */
import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import Modal from '@shared/ui/Modal';
import { Skeleton } from '@shared/ui/Skeleton';
import { Icon } from '@shared/ui/Icon';
import { useToast } from '@shared/ui/Toast';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import { collectionsApi, type Collection } from '@shared/api/collections';
import styles from './CollectionDataPage.module.css';

const PAGE_SIZES = [25, 50, 100];

export default function CollectionDataPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pagination & search
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Upload modal
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  // Checkbox refs for indeterminate state
  const selectAllRef = useRef<HTMLInputElement>(null);
  const selectAllTableRef = useRef<HTMLInputElement>(null);

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Fetch collection info
  const { data: collection, isLoading: collectionLoading } = useQuery({
    queryKey: ['collections', 'detail', slug],
    queryFn: () => collectionsApi.getBySlug(slug!),
    enabled: !!slug,
  });

  // Fetch data
  const offset = (page - 1) * pageSize;
  const { data: dataResult, isLoading: dataLoading, refetch } = useQuery({
    queryKey: ['collections', 'data', slug, page, pageSize, debouncedSearch],
    queryFn: () =>
      collectionsApi.getData(slug!, {
        limit: pageSize,
        offset,
        search: debouncedSearch || undefined,
      }),
    enabled: !!slug,
  });

  const rows = dataResult?.items ?? [];
  const total = dataResult?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  // Update indeterminate state for "select all" checkboxes
  useEffect(() => {
    const isIndeterminate = selectedIds.size > 0 && selectedIds.size < rows.length;
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = isIndeterminate;
    }
    if (selectAllTableRef.current) {
      selectAllTableRef.current.indeterminate = isIndeterminate;
    }
  }, [selectedIds.size, rows.length]);

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) => collectionsApi.deleteRows(slug!, ids),
    onSuccess: data => {
      showToast({ type: 'success', message: `Удалено ${data.deleted} записей` });
      setSelectedIds(new Set());
      queryClient.invalidateQueries({ queryKey: ['collections', 'data', slug] });
      queryClient.invalidateQueries({ queryKey: ['collections', 'detail', slug] });
    },
    onError: (err: Error) => {
      showToast({ type: 'error', message: err.message || 'Ошибка удаления' });
    },
  });

  // Handlers
  const handleSelectAll = useCallback(() => {
    if (rows.length === 0) return;
    if (selectedIds.size === rows.length && selectedIds.size > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(rows.map(r => r._id as number)));
    }
  }, [rows, selectedIds.size]);

  const handleSelectRow = useCallback((id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
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
      const result = await collectionsApi.uploadCSV(slug, uploadFile, {
        skip_errors: true,
      });
      showToast({
        type: 'success',
        message: `Загружено ${result.inserted_rows} записей`,
      });
      if (result.errors.length > 0) {
        showToast({
          type: 'warning',
          message: `${result.errors.length} записей пропущено из-за ошибок`,
        });
      }
      setUploadModalOpen(false);
      setUploadFile(null);
      refetch();
      queryClient.invalidateQueries({ queryKey: ['collections', 'detail', slug] });
    } catch (err) {
      showToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Ошибка загрузки',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleDownloadTemplate = () => {
    if (!slug) return;
    window.open(collectionsApi.downloadTemplate(slug), '_blank');
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
    }
  };

  // Truncate long text
  const truncateText = (text: unknown, maxLen = 100): string => {
    if (text === null || text === undefined) return '—';
    const str = String(text);
    if (str.length <= maxLen) return str;
    return str.substring(0, maxLen) + '...';
  };

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

  // Ensure fields is always an array
  const fields = Array.isArray(collection.fields) ? collection.fields : [];

  return (
    <div className={styles.page}>
      {/* Header */}
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
              <Badge tone="info" size="small">
                {collection.type.toUpperCase()}
              </Badge>
              <span>{total.toLocaleString()} записей</span>
            </div>
          </div>
        </div>
        <div className={styles.headerRight}>
          <Button variant="secondary" onClick={handleDownloadTemplate}>
            <Icon name="download" size={16} />
            Шаблон CSV
          </Button>
          <Button onClick={() => setUploadModalOpen(true)}>
            <Icon name="upload" size={16} />
            Загрузить CSV
          </Button>
        </div>
      </header>

      {/* Toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <label className={styles.selectAll}>
            <input
              ref={selectAllRef}
              type="checkbox"
              checked={rows.length > 0 && selectedIds.size === rows.length}
              onChange={handleSelectAll}
            />
            Выбрать все
          </label>
          {selectedIds.size > 0 && (
            <>
              <span className={styles.selectedCount}>
                Выбрано: {selectedIds.size}
              </span>
              <div className={styles.bulkActions}>
                <Button
                  variant="danger"
                  size="small"
                  onClick={handleDeleteSelected}
                  disabled={deleteMutation.isPending}
                >
                  <Icon name="trash" size={14} />
                  Удалить
                </Button>
              </div>
            </>
          )}
        </div>
        <div className={styles.toolbarRight}>
          <Input
            placeholder="Поиск..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={styles.search}
          />
        </div>
      </div>

      {/* Table */}
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
                : 'Загрузите данные через CSV файл'}
            </p>
            {!debouncedSearch && (
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
                <th className={styles.checkboxCol}>
                  <input
                    ref={selectAllTableRef}
                    type="checkbox"
                    checked={rows.length > 0 && selectedIds.size === rows.length}
                    onChange={handleSelectAll}
                  />
                </th>
                <th>ID</th>
                {fields.map(f => (
                  <th key={f.name}>{f.name.toUpperCase()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const rowId = row._id as number;
                const isSelected = selectedIds.has(rowId);
                return (
                  <tr
                    key={rowId}
                    className={isSelected ? styles.selected : ''}
                  >
                    <td className={styles.checkboxCol}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleSelectRow(rowId)}
                      />
                    </td>
                    <td>{rowId}</td>
                    {fields.map(f => (
                      <td key={f.name} title={String(row[f.name] ?? '')}>
                        <span className={styles.cellTruncate}>
                          {truncateText(row[f.name])}
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

      {/* Pagination */}
      {total > 0 && (
        <div className={styles.pagination}>
          <div className={styles.paginationInfo}>
            Показано {offset + 1}–{Math.min(offset + pageSize, total)} из{' '}
            {total.toLocaleString()}
          </div>
          <div className={styles.paginationControls}>
            <button
              className={styles.paginationBtn}
              onClick={() => setPage(1)}
              disabled={page === 1}
            >
              <Icon name="chevrons-left" size={16} />
            </button>
            <button
              className={styles.paginationBtn}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <Icon name="chevron-left" size={16} />
            </button>
            <span style={{ margin: '0 8px', fontSize: 13 }}>
              Страница {page} из {totalPages}
            </span>
            <button
              className={styles.paginationBtn}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
            >
              <Icon name="chevron-right" size={16} />
            </button>
            <button
              className={styles.paginationBtn}
              onClick={() => setPage(totalPages)}
              disabled={page === totalPages}
            >
              <Icon name="chevrons-right" size={16} />
            </button>
          </div>
          <div className={styles.pageSize}>
            <span>Показывать:</span>
            <select
              value={pageSize}
              onChange={e => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
            >
              {PAGE_SIZES.map(size => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      <Modal
        open={uploadModalOpen}
        onClose={() => {
          setUploadModalOpen(false);
          setUploadFile(null);
        }}
        title="Загрузка CSV"
      >
        <div style={{ padding: 24 }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />

          {!uploadFile ? (
            <div
              className={styles.uploadZone}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className={styles.uploadIcon}>
                <Icon name="upload" size={48} />
              </div>
              <div className={styles.uploadText}>
                Нажмите или перетащите CSV файл
              </div>
              <div className={styles.uploadHint}>
                Поддерживается UTF-8, разделитель — запятая
              </div>
            </div>
          ) : (
            <div>
              <div style={{ marginBottom: 16 }}>
                <strong>Файл:</strong> {uploadFile.name}
              </div>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                <Button
                  variant="secondary"
                  onClick={() => setUploadFile(null)}
                  disabled={uploading}
                >
                  Отмена
                </Button>
                <Button onClick={handleUpload} disabled={uploading}>
                  {uploading ? 'Загрузка...' : 'Загрузить'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}

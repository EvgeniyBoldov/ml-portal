import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { collectionsApi, type Collection, type DiscoveredSqlTable } from '@/shared/api';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

export type SqlDiscoveryItem = DiscoveredSqlTable & { key: string };

interface UseSqlCollectionCatalogResult {
  isSqlCollection: boolean;
  sqlCollectionData: { items: Record<string, unknown>[]; total: number } | undefined;
  sqlCollectionDataLoading: boolean;
  showSqlDiscoveryModal: boolean;
  setShowSqlDiscoveryModal: (open: boolean) => void;
  sqlDiscoveryLoading: boolean;
  sqlDiscoveryItems: SqlDiscoveryItem[];
  sqlDiscoverySelected: Set<string>;
  sqlDiscoverySaving: boolean;
  sqlSelectedRowIds: Set<string>;
  sqlDeleting: boolean;
  existingSqlTableNames: Set<string>;
  setSqlSelectedRowIds: (ids: Set<string>) => void;
  openSqlDiscoveryModal: () => Promise<void>;
  handleSqlDiscoveryToggle: (key: string, checked: boolean) => void;
  addDiscoveredSqlTables: () => Promise<void>;
  deleteSelectedSqlTables: () => Promise<void>;
}

export function useSqlCollectionCatalog(
  collection: Collection | undefined,
  isNew: boolean,
): UseSqlCollectionCatalogResult {
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [showSqlDiscoveryModal, setShowSqlDiscoveryModal] = useState(false);
  const [sqlDiscoveryLoading, setSqlDiscoveryLoading] = useState(false);
  const [sqlDiscoveryItems, setSqlDiscoveryItems] = useState<SqlDiscoveryItem[]>([]);
  const [sqlDiscoverySelected, setSqlDiscoverySelected] = useState<Set<string>>(new Set());
  const [sqlDiscoverySaving, setSqlDiscoverySaving] = useState(false);
  const [sqlSelectedRowIds, setSqlSelectedRowIds] = useState<Set<string>>(new Set());
  const [sqlDeleting, setSqlDeleting] = useState(false);

  const isSqlCollection = collection?.collection_type === 'sql';

  const { data: sqlCollectionData, isLoading: sqlCollectionDataLoading, refetch: refetchSqlCollectionData } = useQuery({
    queryKey: ['collections', 'sql-data', collection?.id ?? ''],
    queryFn: () => collectionsApi.getData(collection!.slug, { limit: 100, offset: 0 }),
    enabled: !isNew && !!collection?.slug && isSqlCollection,
    staleTime: 10_000,
  });

  const existingSqlTableNames = useMemo(() => {
    const items = sqlCollectionData?.items ?? [];
    return new Set<string>(
      items
        .map((row) => String((row as Record<string, unknown>).table_name ?? '').trim().toLowerCase())
        .filter(Boolean),
    );
  }, [sqlCollectionData?.items]);

  const openSqlDiscoveryModal = async () => {
    if (!collection?.id) return;
    setShowSqlDiscoveryModal(true);
    setSqlDiscoveryLoading(true);
    setSqlDiscoverySelected(new Set());
    try {
      const response = await collectionsApi.discoverSqlTables(collection.id);
      const items = response.items.map((item) => ({
        ...item,
        key: `${item.schema_name}.${item.table_name}`,
      }));
      setSqlDiscoveryItems(items);
      const preselected = new Set<string>();
      for (const item of items) {
        const fullName = `${item.schema_name}.${item.table_name}`.trim().toLowerCase();
        if (!existingSqlTableNames.has(fullName)) {
          preselected.add(item.key);
        }
      }
      setSqlDiscoverySelected(preselected);
    } catch (error) {
      showError(error instanceof Error ? error.message : 'Не удалось выполнить SQL discovery');
    } finally {
      setSqlDiscoveryLoading(false);
    }
  };

  const handleSqlDiscoveryToggle = (key: string, checked: boolean) => {
    const item = sqlDiscoveryItems.find((candidate) => candidate.key === key);
    if (!item) return;
    const fullName = `${item.schema_name}.${item.table_name}`.trim().toLowerCase();
    if (existingSqlTableNames.has(fullName)) return;

    setSqlDiscoverySelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const addDiscoveredSqlTables = async () => {
    if (!collection?.slug) return;
    let selectedItems = sqlDiscoveryItems.filter((item) => sqlDiscoverySelected.has(item.key));
    if (!selectedItems.length) {
      selectedItems = sqlDiscoveryItems.filter((item) => {
        const fullName = `${item.schema_name}.${item.table_name}`.trim().toLowerCase();
        return !existingSqlTableNames.has(fullName);
      });
    }
    const uniqueByTable = new Map<string, SqlDiscoveryItem>();
    for (const item of selectedItems) {
      const fullName = `${item.schema_name}.${item.table_name}`.trim();
      if (!fullName) continue;
      const dedupeKey = fullName.toLowerCase();
      if (existingSqlTableNames.has(dedupeKey)) continue;
      if (!uniqueByTable.has(dedupeKey)) {
        uniqueByTable.set(dedupeKey, item);
      }
    }

    const itemsToInsert = Array.from(uniqueByTable.values());
    if (!itemsToInsert.length) {
      showError('Все выбранные таблицы уже добавлены');
      return;
    }

    setSqlDiscoverySaving(true);
    try {
      for (const item of itemsToInsert) {
        await collectionsApi.createRow(
          collection.slug,
          {
            data: {
              table_name: `${item.schema_name}.${item.table_name}`,
              table_schema: item.table_schema ?? {},
            },
          },
          collection.tenant_id,
        );
      }
      await refetchSqlCollectionData();
      showSuccess(`Добавлено таблиц: ${itemsToInsert.length}`);
      setShowSqlDiscoveryModal(false);
    } catch (error) {
      showError(error instanceof Error ? error.message : 'Не удалось добавить выбранные таблицы');
    } finally {
      setSqlDiscoverySaving(false);
    }
  };

  const deleteSelectedSqlTables = async () => {
    if (!collection?.slug || !sqlSelectedRowIds.size) return;
    setSqlDeleting(true);
    try {
      const ids = Array.from(sqlSelectedRowIds);
      await collectionsApi.deleteRows(collection.slug, ids, collection.tenant_id || undefined);
      await refetchSqlCollectionData();
      setSqlSelectedRowIds(new Set());
      showSuccess(`Удалено таблиц: ${ids.length}`);
    } catch (error) {
      showError(error instanceof Error ? error.message : 'Не удалось удалить выбранные таблицы');
    } finally {
      setSqlDeleting(false);
    }
  };

  return {
    isSqlCollection,
    sqlCollectionData,
    sqlCollectionDataLoading,
    showSqlDiscoveryModal,
    setShowSqlDiscoveryModal,
    sqlDiscoveryLoading,
    sqlDiscoveryItems,
    sqlDiscoverySelected,
    sqlDiscoverySaving,
    sqlSelectedRowIds,
    sqlDeleting,
    existingSqlTableNames,
    setSqlSelectedRowIds,
    openSqlDiscoveryModal,
    handleSqlDiscoveryToggle,
    addDiscoveredSqlTables,
    deleteSelectedSqlTables,
  };
}

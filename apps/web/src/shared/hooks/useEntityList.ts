/**
 * useEntityList - Universal hook for entity list pages
 *
 * Encapsulates:
 * - List query with optional params
 * - Client-side search filtering
 * - Delete mutation with cache invalidation
 * - Navigation helper
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

export interface EntityListConfig<TItem> {
  queryKey: QueryKey;
  queryFn: () => Promise<TItem[]>;
  deleteFn?: (id: string) => Promise<void>;
  invalidateKeys?: QueryKey[];
  searchFields?: (keyof TItem)[];
  messages?: {
    deleted?: string;
  };
  basePath: string;
  idField?: keyof TItem;
}

export function useEntityList<TItem extends Record<string, any>>(
  config: EntityListConfig<TItem>
) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [search, setSearch] = useState('');

  const { data: items = [], isLoading, error } = useQuery({
    queryKey: config.queryKey,
    queryFn: config.queryFn,
  });

  const filtered = useMemo(() => {
    if (!search.trim() || !config.searchFields?.length) return items;
    const q = search.toLowerCase();
    return items.filter((item) =>
      config.searchFields!.some((field) =>
        String(item[field] ?? '').toLowerCase().includes(q)
      )
    );
  }, [items, search, config.searchFields]);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => {
      if (!config.deleteFn) return Promise.resolve();
      return config.deleteFn(id);
    },
    onSuccess: () => {
      const keys = config.invalidateKeys ?? [config.queryKey];
      keys.forEach((key) => queryClient.invalidateQueries({ queryKey: [...key] as unknown[] }));
      showSuccess(config.messages?.deleted ?? 'Удалено');
    },
    onError: (err: Error) => showError(err.message),
  });

  const goToCreate = () => navigate(`${config.basePath}/new`);
  const goToDetail = (item: TItem) => {
    const id = item[config.idField ?? 'slug'] ?? item['id'];
    navigate(`${config.basePath}/${id}`);
  };

  return {
    items,
    filtered,
    isLoading,
    error,
    search,
    setSearch,
    deleteMutation,
    goToCreate,
    goToDetail,
  };
}

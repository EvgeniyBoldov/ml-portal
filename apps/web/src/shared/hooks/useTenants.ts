import { useInfiniteQuery } from '@tanstack/react-query';
import { qk } from '@shared/api/keys';
import { tenantApi } from '@shared/api/tenant';

const TENANTS_PAGE_SIZE = 100;

export function useTenants(includeDeprecated = false, search?: string) {
  const query = useInfiniteQuery({
    queryKey: qk.admin.tenants.list({
      size: TENANTS_PAGE_SIZE,
      search: search?.trim() || undefined,
      include_deprecated: includeDeprecated,
    }),
    initialPageParam: 1,
    queryFn: ({ pageParam }) => tenantApi.getTenants({
      page: pageParam,
      size: TENANTS_PAGE_SIZE,
      search: search?.trim() || undefined,
      include_deprecated: includeDeprecated,
    }),
    getNextPageParam: lastPage => lastPage.has_more ? lastPage.page + 1 : undefined,
    staleTime: 60_000,
  });

  return {
    tenants: query.data?.pages.flatMap(page => page.items) ?? [],
    loading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
    hasNextPage: query.hasNextPage,
    fetchNextPage: query.fetchNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
  };
}

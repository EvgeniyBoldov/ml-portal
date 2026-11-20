/**
 * TanStack Query hooks for admin operations
 */
import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  keepPreviousData,
} from '@tanstack/react-query';
import {
  adminApi,
  type UserCreate,
  type UserUpdate,
  type User,
  type TenantCreate,
  type TenantUpdate,
  type Tenant,
  
} from '../admin';
import { qk } from '@shared/api/keys';

// ============================================================================
// Users
// ============================================================================

export interface UseUsersParams {
  query?: string;
  role?: string;
  is_active?: boolean;
  include_deprecated?: boolean;
  limit?: number;
}

export function useUsers(params: UseUsersParams = {}) {
  return useInfiniteQuery({
    queryKey: qk.admin.users.list({ q: params.query, limit: params.limit }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => adminApi.getUsers({ ...params, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.next_cursor : undefined,
    staleTime: 60000, // 1 minute for lists
  });
}

export function useUser(id: string | undefined) {
  return useQuery({
    queryKey: id ? qk.admin.users.detail(id) : ['admin', 'users', 'undefined'],
    queryFn: () => adminApi.getUser(id!),
    enabled: !!id,
    staleTime: 30000, // 30 seconds for detail
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UserCreate) => adminApi.createUser(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.users.all() });
    },
  });
}


export function useUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation<User, Error, { id: string; data: UserUpdate }>({
    mutationFn: ({ id, data }: { id: string; data: UserUpdate }) =>
      adminApi.updateUser(id, data),
    onSuccess: (
      _updatedUser: User,
      variables: { id: string; data: UserUpdate }
    ) => {
      queryClient.invalidateQueries({ queryKey: qk.admin.users.all() });
      queryClient.invalidateQueries({
        queryKey: qk.admin.users.detail(variables.id),
      });
    },
  });
}

export function useSetUserPassword() {
  return useMutation<{ ok: boolean }, Error, { id: string; newPassword: string }>({
    mutationFn: ({ id, newPassword }) => adminApi.setUserPassword(id, newPassword),
  });
}

// ============================================================================
// Models (New Architecture)
// ============================================================================

export interface UseModelsParams {
  type?: string;           // Changed: modality → type
  status?: string;         // Changed: state → status
  enabled_only?: boolean;  // New
  search?: string;
  page?: number;
  size?: number;
}

export function useModels(params: UseModelsParams = {}) {
  return useQuery({
    queryKey: qk.admin.models.list({
      page: params.page,
      size: params.size,
      type: params.type,
      enabled_only: params.enabled_only,
      status: params.status,
      search: params.search,
    }),
    queryFn: () => adminApi.getModels(params),
    staleTime: 60000, // 1 minute for lists
    placeholderData: keepPreviousData,
  });
}






// ============================================================================
// Tenants
// ============================================================================


export function useTenant(id: string | undefined) {
  return useQuery({
    queryKey: id ? qk.admin.tenants.detail(id) : ['admin', 'tenants', 'undefined'],
    queryFn: () => adminApi.getTenant(id!),
    enabled: !!id,
    staleTime: 30000, // 30 seconds for detail
  });
}

export function useCreateTenant() {
  const queryClient = useQueryClient();

  return useMutation<Tenant, Error, TenantCreate>({
    mutationFn: (data: TenantCreate) => adminApi.createTenant(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
    },
  });
}

export function useUpdateTenant() {
  const queryClient = useQueryClient();

  return useMutation<Tenant, Error, { id: string; data: TenantUpdate }>({
    mutationFn: ({ id, data }: { id: string; data: TenantUpdate }) =>
      adminApi.updateTenant(id, data),
    onSuccess: (
      _tenant: Tenant,
      variables: { id: string; data: TenantUpdate }
    ) => {
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
      queryClient.invalidateQueries({
        queryKey: qk.admin.tenants.detail(variables.id),
      });
    },
  });
}

// ============================================================================
// Audit
// ============================================================================



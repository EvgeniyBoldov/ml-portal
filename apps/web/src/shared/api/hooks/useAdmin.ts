/**
 * TanStack Query hooks for admin operations
 */
import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query';
import {
  adminApi,
  type UserCreate,
  type UserUpdate,
  type UserListResponse,
  type User,
  type TenantCreate,
  type TenantUpdate,
  type Tenant,
  type EmailSettings,
  type EmailSettingsUpdate,
} from '../admin';
import { qk } from '@shared/api/keys';

// ============================================================================
// Users
// ============================================================================

export interface UseUsersParams {
  query?: string;
  role?: string;
  is_active?: boolean;
  limit?: number;
  cursor?: string;
}

export function useUsers(params: UseUsersParams = {}) {
  return useQuery({
    queryKey: qk.admin.users({ page: params.cursor ? undefined : 1, q: params.query }),
    queryFn: () => adminApi.getUsers(params),
    staleTime: 60000, // 1 minute for lists
    keepPreviousData: true,
  });
}

export function useUser(id: string | undefined) {
  return useQuery({
    queryKey: id ? qk.admin.user(id) : ['admin', 'user', 'undefined'],
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
      queryClient.invalidateQueries({ queryKey: qk.admin.users() });
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
      queryClient.invalidateQueries({ queryKey: qk.admin.users() });
      queryClient.invalidateQueries({
        queryKey: qk.admin.user(variables.id),
      });
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id: string) => adminApi.deleteUser(id),
    onSuccess: async (_result: void, id: string) => {
      const queries = queryClient.getQueriesData<UserListResponse>({
        queryKey: qk.admin.users(),
      }) as Array<[QueryKey, UserListResponse | undefined]>;
      queries.forEach(([queryKey, data]) => {
        if (!data) return;
        queryClient.setQueryData<UserListResponse>(queryKey, {
          ...data,
          users: data.users.filter(user => user.id !== id),
          total:
            typeof data.total === 'number'
              ? Math.max(0, data.total - 1)
              : data.total,
        });
      });

      await queryClient.invalidateQueries({
        queryKey: qk.admin.users(),
        exact: false,
      });
      queryClient.removeQueries({
        queryKey: qk.admin.user(id),
        exact: true,
      });
    },
  });
}

// ============================================================================
// Models
// ============================================================================

export interface UseModelsParams {
  state?: string;
  modality?: string;
  search?: string;
  page?: number;
  size?: number;
}

export function useModels(params: UseModelsParams = {}) {
  return useQuery({
    queryKey: qk.admin.models(),
    queryFn: () => adminApi.getModels(params),
    staleTime: 60000, // 1 minute for lists
    keepPreviousData: true,
  });
}

export function useScanModels() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => adminApi.scanModels(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models() });
    },
  });
}

export function useRetireModel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: {
      id: string;
      drop_vectors: boolean;
      remove_from_tenants: boolean;
    }) => adminApi.retireModel(params.id, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.models() });
    },
  });
}

export function useModelTenants(id: string | undefined) {
  return useQuery({
    queryKey: ['admin', 'models', id, 'tenants'],
    queryFn: () => adminApi.getModelTenants(id!),
    enabled: !!id,
    staleTime: 30000, // 30 seconds for detail
  });
}

// ============================================================================
// Tenants
// ============================================================================

export function useTenants() {
  return useQuery({
    queryKey: qk.admin.tenants(),
    queryFn: () => adminApi.getTenants(),
    staleTime: 60000, // 1 minute for lists
  });
}

export function useTenant(id: string | undefined) {
  return useQuery({
    queryKey: id ? qk.admin.tenant(id) : ['admin', 'tenant', 'undefined'],
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
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants() });
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
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants() });
      queryClient.invalidateQueries({
        queryKey: qk.admin.tenant(variables.id),
      });
    },
  });
}

// ============================================================================
// Audit
// ============================================================================

export interface UseAuditParams {
  actor_user_id?: string;
  action?: string;
  object_type?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  cursor?: string;
}

export function useAuditLog(params: UseAuditParams = {}) {
  return useQuery({
    queryKey: qk.admin.audit({ page: params.cursor ? undefined : 1 }),
    queryFn: () => adminApi.getAuditLogs(params),
    staleTime: 60000, // 1 minute for lists
    keepPreviousData: true,
  });
}

// ============================================================================
// Email Settings
// ============================================================================

export function useEmailSettings() {
  return useQuery<EmailSettings>({
    queryKey: ['admin', 'email-settings'],
    queryFn: () => adminApi.getEmailSettings(),
    staleTime: 30000, // 30 seconds for detail
  });
}

export function useUpdateEmailSettings() {
  const queryClient = useQueryClient();

  return useMutation<EmailSettings, Error, EmailSettingsUpdate>({
    mutationFn: (data: EmailSettingsUpdate) =>
      adminApi.updateEmailSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'email-settings'] });
    },
  });
}

/**
 * RBAC utilities for frontend authorization checks
 */

export type Role = 'admin' | 'editor' | 'reader';
export type Action =
  | 'users:create'
  | 'users:update'
  | 'users:delete'
  | 'users:view'
  | 'models:manage'
  | 'models:view'
  | 'tenants:create'
  | 'tenants:update'
  | 'tenants:delete'
  | 'tenants:view'
  | 'rag:upload'
  | 'rag:delete'
  | 'rag:view'
  | 'rag:ingest'
  | 'rag:manage'
  | 'audit:view'
  | 'settings:view'
  | 'settings:update';

export interface RbacContext {
  currentUserRole: Role;
  tenantId?: string;
}

/**
 * Check if action is allowed for role
 */
export function can(action: Action, role: Role): boolean {
  // Admin has all permissions
  if (role === 'admin') {
    return true;
  }

  // Role-specific permissions
  const permissions: Record<Role, Action[]> = {
    admin: [], // admin has all permissions via early return
    editor: [
      'users:view',
      'models:view',
      'tenants:view',
      'rag:view',
      'rag:upload',
      'rag:ingest',
      'audit:view',
      'settings:view',
    ],
    reader: [
      'users:view',
      'models:view',
      'tenants:view',
      'rag:view',
      'audit:view',
    ],
  };

  return permissions[role]?.includes(action) ?? false;
}

/**
 * Get reason why action is not allowed
 */
export function getPermissionDeniedReason(action: Action, role: Role): string {
  if (role === 'admin') {
    return '';
  }

  const reasonMap: Record<string, string> = {
    'users:create': 'Требуется роль Admin',
    'users:update': 'Требуется роль Admin',
    'users:delete': 'Требуется роль Admin',
    'models:manage': 'Требуется роль Admin',
    'tenants:create': 'Требуется роль Admin',
    'tenants:update': 'Требуется роль Admin',
    'tenants:delete': 'Требуется роль Admin',
    'rag:delete': 'Требуется роль Editor или выше',
    'rag:manage': 'Требуется роль Editor или выше',
    'settings:update': 'Требуется роль Editor или выше',
  };

  return reasonMap[action] || 'Недостаточно прав';
}

/**
 * Hook-style permission check
 */
export function useCan(action: Action, context: RbacContext): boolean {
  return can(action, context.currentUserRole);
}

export function useCanTooltip(action: Action, context: RbacContext): string {
  if (can(action, context.currentUserRole)) {
    return '';
  }
  return getPermissionDeniedReason(action, context.currentUserRole);
}

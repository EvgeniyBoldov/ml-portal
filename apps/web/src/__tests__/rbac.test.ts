import { describe, it, expect } from 'vitest';
import {
  can,
  getPermissionDeniedReason,
  useCan,
  useCanTooltip,
  type Role,
  type Action,
} from '@shared/lib/rbac';

describe('RBAC', () => {
  describe('can()', () => {
    describe('admin role', () => {
      it('should allow all actions for admin', () => {
        const actions: Action[] = [
          'users:create',
          'users:update',
          'users:delete',
          'users:view',
          'models:manage',
          'models:view',
          'tenants:create',
          'tenants:update',
          'tenants:delete',
          'tenants:view',
          'rag:upload',
          'rag:delete',
          'rag:view',
          'rag:ingest',
          'rag:manage',
          'audit:view',
          'settings:view',
          'settings:update',
        ];

        actions.forEach(action => {
          expect(can(action, 'admin')).toBe(true);
        });
      });
    });

    describe('editor role', () => {
      it('should allow view actions', () => {
        expect(can('users:view', 'editor')).toBe(true);
        expect(can('models:view', 'editor')).toBe(true);
        expect(can('tenants:view', 'editor')).toBe(true);
        expect(can('rag:view', 'editor')).toBe(true);
        expect(can('audit:view', 'editor')).toBe(true);
        expect(can('settings:view', 'editor')).toBe(true);
      });

      it('should allow rag upload and ingest', () => {
        expect(can('rag:upload', 'editor')).toBe(true);
        expect(can('rag:ingest', 'editor')).toBe(true);
      });

      it('should deny admin-only actions', () => {
        expect(can('users:create', 'editor')).toBe(false);
        expect(can('users:update', 'editor')).toBe(false);
        expect(can('users:delete', 'editor')).toBe(false);
        expect(can('models:manage', 'editor')).toBe(false);
        expect(can('tenants:create', 'editor')).toBe(false);
        expect(can('tenants:update', 'editor')).toBe(false);
        expect(can('tenants:delete', 'editor')).toBe(false);
      });

      it('should deny rag delete and manage', () => {
        expect(can('rag:delete', 'editor')).toBe(false);
        expect(can('rag:manage', 'editor')).toBe(false);
      });

      it('should deny settings update', () => {
        expect(can('settings:update', 'editor')).toBe(false);
      });
    });

    describe('reader role', () => {
      it('should allow only view actions', () => {
        expect(can('users:view', 'reader')).toBe(true);
        expect(can('models:view', 'reader')).toBe(true);
        expect(can('tenants:view', 'reader')).toBe(true);
        expect(can('rag:view', 'reader')).toBe(true);
        expect(can('audit:view', 'reader')).toBe(true);
      });

      it('should deny upload and ingest', () => {
        expect(can('rag:upload', 'reader')).toBe(false);
        expect(can('rag:ingest', 'reader')).toBe(false);
      });

      it('should deny all modify actions', () => {
        expect(can('users:create', 'reader')).toBe(false);
        expect(can('users:update', 'reader')).toBe(false);
        expect(can('users:delete', 'reader')).toBe(false);
        expect(can('models:manage', 'reader')).toBe(false);
        expect(can('tenants:create', 'reader')).toBe(false);
        expect(can('tenants:update', 'reader')).toBe(false);
        expect(can('tenants:delete', 'reader')).toBe(false);
        expect(can('rag:delete', 'reader')).toBe(false);
        expect(can('rag:manage', 'reader')).toBe(false);
        expect(can('settings:view', 'reader')).toBe(false);
        expect(can('settings:update', 'reader')).toBe(false);
      });
    });
  });

  describe('getPermissionDeniedReason()', () => {
    it('should return empty string for admin', () => {
      expect(getPermissionDeniedReason('users:create', 'admin')).toBe('');
      expect(getPermissionDeniedReason('rag:delete', 'admin')).toBe('');
    });

    it('should return reason for admin-only actions', () => {
      expect(getPermissionDeniedReason('users:create', 'editor')).toContain('Admin');
      expect(getPermissionDeniedReason('users:update', 'reader')).toContain('Admin');
      expect(getPermissionDeniedReason('users:delete', 'editor')).toContain('Admin');
      expect(getPermissionDeniedReason('models:manage', 'reader')).toContain('Admin');
      expect(getPermissionDeniedReason('tenants:create', 'editor')).toContain('Admin');
    });

    it('should return reason for editor-level actions', () => {
      expect(getPermissionDeniedReason('rag:delete', 'reader')).toContain('Editor');
      expect(getPermissionDeniedReason('rag:manage', 'reader')).toContain('Editor');
      expect(getPermissionDeniedReason('settings:update', 'reader')).toContain('Editor');
    });

    it('should return generic message for unknown actions', () => {
      // @ts-expect-error - testing unknown action
      expect(getPermissionDeniedReason('unknown:action', 'reader')).toBe('Недостаточно прав');
    });
  });

  describe('useCan()', () => {
    it('should check permission based on context role', () => {
      expect(useCan('users:create', { currentUserRole: 'admin' })).toBe(true);
      expect(useCan('users:create', { currentUserRole: 'editor' })).toBe(false);
      expect(useCan('users:create', { currentUserRole: 'reader' })).toBe(false);
    });

    it('should work with tenantId in context', () => {
      expect(
        useCan('rag:view', { currentUserRole: 'reader', tenantId: 'tenant-123' })
      ).toBe(true);
    });
  });

  describe('useCanTooltip()', () => {
    it('should return empty string when action is allowed', () => {
      expect(useCanTooltip('users:create', { currentUserRole: 'admin' })).toBe('');
      expect(useCanTooltip('rag:view', { currentUserRole: 'reader' })).toBe('');
    });

    it('should return reason when action is denied', () => {
      expect(useCanTooltip('users:create', { currentUserRole: 'editor' })).toContain('Admin');
      expect(useCanTooltip('rag:delete', { currentUserRole: 'reader' })).toContain('Editor');
    });
  });
});

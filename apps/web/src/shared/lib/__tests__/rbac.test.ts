import {
  can,
  getPermissionDeniedReason,
  useCan,
  useCanTooltip,
  type RbacContext,
} from '@/shared/lib/rbac';

describe('rbac permissions', () => {
  const editorContext: RbacContext = { currentUserRole: 'editor' };
  const readerContext: RbacContext = { currentUserRole: 'reader' };

  it('allows admin for any action', () => {
    expect(can('users:create', 'admin')).toBe(true);
    expect(can('settings:update', 'admin')).toBe(true);
  });

  it('allows editor for upload and denies delete', () => {
    expect(can('rag:upload', 'editor')).toBe(true);
    expect(can('rag:delete', 'editor')).toBe(false);
  });

  it('restricts reader write actions', () => {
    expect(can('users:view', 'reader')).toBe(true);
    expect(can('tenants:update', 'reader')).toBe(false);
  });

  it('returns localized denial reason', () => {
    expect(getPermissionDeniedReason('users:create', 'reader')).toBe(
      'Требуется роль Admin'
    );
    expect(getPermissionDeniedReason('settings:update', 'reader')).toBe(
      'Требуется роль Editor или выше'
    );
  });

  it('useCan and useCanTooltip mirror can() result', () => {
    expect(useCan('rag:upload', editorContext)).toBe(true);
    expect(useCan('tenants:delete', readerContext)).toBe(false);
    expect(useCanTooltip('tenants:delete', readerContext)).toBe(
      'Требуется роль Admin'
    );
    expect(useCanTooltip('users:view', readerContext)).toBe('');
  });
});

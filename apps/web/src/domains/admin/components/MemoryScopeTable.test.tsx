import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DataTable } from '@/shared/ui';
import type { MemoryScopeAdminItem } from '@/shared/api/admin';
import { scopeColumns, type ScopeTableRow } from './MemoryScopeTable';

const scope: MemoryScopeAdminItem = {
  id: 'scope-1', scope_type: 'project', key: 'platform', name: 'Платформа', aliases: [],
  is_all: false, project_id: 'project-1', project_type: 'platform', lifecycle_status: 'active', retention_days: 14,
};

const row: ScopeTableRow = {
  kind: 'published', id: 'scope:scope-1', scope_type: 'project', key: scope.key,
  name: scope.name, aliases: scope.aliases, status: 'active', scope,
};

afterEach(cleanup);

describe('MemoryScopeTable actions', () => {
  it('opens edit and delete only from the row action menu', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const onLifecycle = vi.fn();
    const columns = scopeColumns({ onReview: vi.fn(), onEdit, onLifecycle });
    render(<DataTable columns={columns} data={[row]} keyField="id" />);

    await user.click(screen.getByRole('button', { name: 'Действия со скоупом Платформа' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Изменить' }));
    expect(onEdit).toHaveBeenCalledWith(scope);

    await user.click(screen.getByRole('button', { name: 'Действия со скоупом Платформа' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Удалить' }));
    expect(onLifecycle).toHaveBeenCalledWith(scope, 'delete');
  });

  it('offers restore for deprecated scopes', () => {
    const onLifecycle = vi.fn();
    const deprecatedRow = { ...row, status: 'deprecated', scope: { ...scope, lifecycle_status: 'deprecated' as const } };
    const columns = scopeColumns({ onReview: vi.fn(), onEdit: vi.fn(), onLifecycle });
    render(<DataTable columns={columns} data={[deprecatedRow]} keyField="id" />);

    fireEvent.click(screen.getByRole('button', { name: 'Действия со скоупом Платформа' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Восстановить' }));
    expect(onLifecycle).toHaveBeenCalledWith(deprecatedRow.scope, 'restore');
  });
});

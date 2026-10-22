import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock('react-router-dom', async importOriginal => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mocks.navigate,
}));
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    data: [
      {
        id: 'conn-1',
        name: 'Inventory API',
        slug: 'inventory-api',
        connector_type: 'data',
        connector_subtype: 'api',
        is_active: true,
        health_status: 'healthy',
        created_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'conn-2',
        name: 'Billing MCP',
        slug: 'billing-mcp',
        connector_type: 'mcp',
        connector_subtype: null,
        is_active: false,
        health_status: 'unknown',
        created_at: '2026-01-02T00:00:00Z',
      },
    ],
    isLoading: false,
    error: null,
  }),
}));
vi.mock('@/shared/api', () => ({ toolInstancesApi: { list: vi.fn() } }));
vi.mock('@/shared/ui/EntityPage', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/EntityPage')>()),
  EntityPageV2: ({
    children,
    title,
    headerActions,
    actionButtons,
  }: React.PropsWithChildren<{
    title: string;
    headerActions?: React.ReactNode;
    actionButtons?: React.ReactNode;
  }>) => (
    <main>
      <h1>{title}</h1>
      {headerActions}
      {actionButtons}
      {children}
    </main>
  ),
  Tab: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
}));
vi.mock('@/shared/ui', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/ui')>();
  return {
    ...actual,
    DataTable: ({
      data,
      onRowClick,
    }: {
      data: Array<{ id: string; name: string }>;
      onRowClick: (item: { id: string }) => void;
    }) => (
      <div>
        {data.map(item => (
          <button key={item.id} onClick={() => onRowClick(item)}>
            {item.name}
          </button>
        ))}
      </div>
    ),
  };
});

import { InstancesListPage } from './InstancesListPage';

afterEach(() => {
  cleanup();
  mocks.navigate.mockClear();
});

describe('InstancesListPage', () => {
  it('filters connectors by name and navigates to the selected connector', () => {
    render(
      <MemoryRouter>
        <InstancesListPage />
      </MemoryRouter>
    );

    expect(
      screen.getByRole('button', { name: 'Inventory API' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Billing MCP' })
    ).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Поиск коннекторов...'), {
      target: { value: 'billing' },
    });
    expect(
      screen.queryByRole('button', { name: 'Inventory API' })
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Billing MCP' }));
    expect(mocks.navigate).toHaveBeenCalledWith('/admin/connectors/conn-2');
  });
});

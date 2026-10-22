import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  query: { data: undefined as unknown, isLoading: false, isError: false, refetch: vi.fn() },
  mutation: { isPending: false, isError: false, mutate: vi.fn() },
  invalidateQueries: vi.fn(),
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => mocks.query,
  useMutation: () => mocks.mutation,
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries, setQueryData: vi.fn() }),
}));
vi.mock('@/shared/api/keys', () => ({ qk: { discoveredTools: { all: () => [], list: () => [], detail: () => [] } } }));
vi.mock('@/shared/api/discoveredTools', () => ({ discoveredToolsApi: { list: vi.fn(), get: vi.fn(), update: vi.fn(), rescan: vi.fn() } }));
vi.mock('@/shared/ui/EntityPage', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/EntityPage')>()),
  EntityPageV2: ({ children, title, actionButtons, onSave }: React.PropsWithChildren<{ title: string; actionButtons?: React.ReactNode; onSave?: () => void }>) => (
    <main><h1>{title}</h1>{actionButtons}{onSave && <button onClick={onSave}>Сохранить</button>}{children}</main>
  ),
  Tab: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
}));
vi.mock('@/shared/ui/GridLayout', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/ui/GridLayout')>()),
  Block: () => null,
}));
vi.mock('@/shared/ui', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/ui')>();
  return { ...actual, DataTable: ({ emptyText }: { emptyText: string }) => <div>{emptyText}</div> };
});

import { DiscoveredToolViewPage } from './DiscoveredToolViewPage';
import { DiscoveredToolsPage } from './DiscoveredToolsPage';

afterEach(() => {
  cleanup();
  mocks.query = { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
  mocks.mutation = { isPending: false, isError: false, mutate: vi.fn() };
  vi.clearAllMocks();
});

describe('discovered tools pages error states', () => {
  it('shows a retry action when the list request fails instead of reporting an empty registry', () => {
    mocks.query.isError = true;
    const refetch = vi.fn();
    mocks.query.refetch = refetch;
    render(<MemoryRouter><DiscoveredToolsPage /></MemoryRouter>);

    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось загрузить инструменты');
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(refetch).toHaveBeenCalledOnce();
    expect(screen.getAllByText('Не удалось загрузить инструменты.', { exact: true })).toHaveLength(2);
  });

  it('reports a failed rescan', () => {
    mocks.mutation.isError = true;
    render(<MemoryRouter><DiscoveredToolsPage /></MemoryRouter>);

    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось выполнить сканирование');
  });

  it('shows a retry action when a tool detail request fails', () => {
    mocks.query.isError = true;
    const refetch = vi.fn();
    mocks.query.refetch = refetch;
    render(<MemoryRouter><DiscoveredToolViewPage /></MemoryRouter>);

    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось загрузить инструмент');
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it('reports a failed risk update', () => {
    mocks.query.data = {
      id: 'tool-id', slug: 'lookup', name: 'Lookup', source: 'mcp', domains: [],
      description: null, risk_level: null, connector_name: null, connector_slug: null,
      input_schema: {}, output_schema: {}, is_active: true,
    };
    mocks.mutation.isError = true;
    render(<MemoryRouter><DiscoveredToolViewPage /></MemoryRouter>);

    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось сохранить уровень риска');
  });
});

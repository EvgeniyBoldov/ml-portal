import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  discoveredToolsApi,
  type DiscoveredToolDetail,
} from '@/shared/api/discoveredTools';
import { ToastProvider } from '@/shared/ui/Toast';
import { DiscoveredToolViewPage } from './DiscoveredToolViewPage';
import { DiscoveredToolsPage } from './DiscoveredToolsPage';

vi.mock('@/shared/api/discoveredTools', () => ({
  discoveredToolsApi: {
    list: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    rescan: vi.fn(),
  },
}));

const tool: DiscoveredToolDetail = {
  id: 'tool-1',
  slug: 'lookup',
  name: 'Lookup',
  source: 'mcp',
  provider_instance_id: 'provider-1',
  connector_name: 'Jira MCP',
  connector_slug: 'jira-mcp',
  domains: [],
  source_types: ['api'],
  description: 'Find an issue by key',
  risk_level: null,
  result_delivery: 'direct',
  input_schema: { type: 'object' },
  output_schema: null,
  observed_data_schema: null,
  has_observed_data_schema: false,
  is_active: true,
  last_seen_at: null,
  created_at: '',
  updated_at: '',
};

function mount(path = '/admin/tools') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/admin/tools" element={<DiscoveredToolsPage />} />
            <Route
              path="/admin/tools/discovered/:id"
              element={<DiscoveredToolViewPage />}
            />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.mocked(discoveredToolsApi.list).mockResolvedValue([tool]);
  vi.mocked(discoveredToolsApi.get).mockResolvedValue(tool);
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('tools registry', () => {
  it('sorts risk by severity and reverses the order on a second click', async () => {
    vi.mocked(discoveredToolsApi.list).mockResolvedValue([
      { ...tool, id: 'risky', name: 'Tool risky', risk_level: 'risky' },
      { ...tool, id: 'unclassified', name: 'Tool unclassified' },
      { ...tool, id: 'safe', name: 'Tool safe', risk_level: 'safe' },
      { ...tool, id: 'default', name: 'Tool default', source: 'local' },
    ]);
    mount();
    await screen.findByRole('link', { name: 'Tool safe' });

    const riskHeader = screen.getByText('Риск', { exact: true });
    const toolNames = () =>
      screen
        .getAllByRole('link', { name: /^Tool / })
        .map(link => link.textContent);
    fireEvent.click(riskHeader);
    expect(toolNames()).toEqual([
      'Tool safe',
      'Tool default',
      'Tool unclassified',
      'Tool risky',
    ]);
    fireEvent.click(riskHeader);
    expect(toolNames()).toEqual([
      'Tool risky',
      'Tool unclassified',
      'Tool default',
      'Tool safe',
    ]);
  });

  it('combines URL filters and search and preserves them in the detail link', async () => {
    vi.mocked(discoveredToolsApi.list).mockResolvedValue([
      tool,
      {
        ...tool,
        id: 'other',
        name: 'Other',
        provider_instance_id: 'provider-2',
        source_types: ['sql'],
      },
    ]);
    mount('/admin/tools?type=api&provider=provider-1');
    const link = await screen.findByRole('link', { name: 'Lookup' });
    expect(link).toHaveAttribute(
      'href',
      '/admin/tools/discovered/tool-1?type=api&provider=provider-1'
    );
    expect(screen.getByRole('link', { name: 'Jira MCP' })).toHaveAttribute(
      'href',
      '/admin/connectors/provider-1'
    );
    expect(screen.queryByRole('link', { name: 'Other' })).toBeNull();
    expect(screen.getByText('Требует классификации')).toBeVisible();

    fireEvent.change(
      screen.getByRole('searchbox', { name: 'Поиск инструментов' }),
      { target: { value: 'unknown' } }
    );
    expect(screen.getByText('Ничего не найдено')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить фильтры' }));
    expect(screen.getByRole('link', { name: 'Other' })).toBeVisible();
  });

  it('shows a retry action when loading the registry fails', async () => {
    vi.mocked(discoveredToolsApi.list).mockRejectedValueOnce(
      new Error('offline')
    );
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось загрузить инструменты'
    );
    expect(screen.queryByText('Инструменты ещё не обнаружены')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByRole('link', { name: 'Lookup' })).toBeVisible();
  });

  it('scans only the selected MCP provider and reports a partial failure', async () => {
    vi.mocked(discoveredToolsApi.rescan).mockResolvedValue({
      message: 'Scan complete',
      stats: { mcp_failed_providers: [{ provider_slug: 'jira-mcp' }] },
    });
    mount('/admin/tools?provider=provider-1');
    await screen.findByRole('link', { name: 'Lookup' });
    fireEvent.click(
      screen.getByRole('button', { name: /^Сканировать источники$/ })
    );
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Будет опрошен только «Jira MCP»'
    );
    fireEvent.click(screen.getByRole('button', { name: /^Сканировать$/ }));
    expect(
      await screen.findByText('Не удалось опросить: jira-mcp.')
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Обновить' })).toBeNull();
    expect(discoveredToolsApi.rescan).toHaveBeenCalledWith({
      include_local: false,
      provider_instance_id: 'provider-1',
    });
  });
});

describe('tool settings', () => {
  it('saves the MCP risk classification independently of delivery', async () => {
    const scrollIntoView = Object.getOwnPropertyDescriptor(
      window.Element.prototype,
      'scrollIntoView'
    );
    Object.defineProperty(window.Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    try {
      const updated = { ...tool, risk_level: 'risky' } as const;
      vi.mocked(discoveredToolsApi.update).mockResolvedValue(updated);
      mount('/admin/tools/discovered/tool-1');
      fireEvent.click(
        await screen.findByRole('button', { name: 'Изменить настройки' })
      );
      fireEvent.click(
        screen.getByRole('combobox', { name: 'Классификация риска' })
      );
      fireEvent.click(screen.getByRole('option', { name: 'Рискованный' }));
      vi.mocked(discoveredToolsApi.get).mockResolvedValue(updated);
      fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
      expect(
        await screen.findByRole('button', { name: 'Изменить настройки' })
      ).toBeVisible();
      expect(discoveredToolsApi.update).toHaveBeenCalledWith('tool-1', {
        risk_level: 'risky',
      });
      expect(screen.getByText('Рискованный')).toBeVisible();
    } finally {
      if (scrollIntoView)
        Object.defineProperty(
          window.Element.prototype,
          'scrollIntoView',
          scrollIntoView
        );
      else Reflect.deleteProperty(window.Element.prototype, 'scrollIntoView');
    }
  });

  it('shows a retry action when loading the detail fails', async () => {
    vi.mocked(discoveredToolsApi.get).mockRejectedValueOnce(
      new Error('offline')
    );
    mount('/admin/tools/discovered/tool-1');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось загрузить инструмент'
    );
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(
      await screen.findByRole('heading', { name: 'Lookup' })
    ).toBeVisible();
  });

  it('retains the delivery change after a failed save and only sends the changed setting', async () => {
    vi.mocked(discoveredToolsApi.update).mockRejectedValueOnce(
      new Error('save failed')
    );
    mount('/admin/tools/discovered/tool-1?provider=provider-1');
    fireEvent.click(
      await screen.findByRole('button', { name: 'Изменить настройки' })
    );
    const toggle = screen.getByRole('checkbox', {
      name: 'Сохранять ответ как набор данных',
    });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось сохранить настройки инструмента'
    );
    expect(toggle).toBeChecked();
    expect(discoveredToolsApi.update).toHaveBeenCalledWith('tool-1', {
      result_delivery: 'store',
    });

    vi.mocked(discoveredToolsApi.update).mockResolvedValueOnce({
      ...tool,
      result_delivery: 'store',
    });
    vi.mocked(discoveredToolsApi.get).mockResolvedValue({
      ...tool,
      result_delivery: 'store',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(screen.queryByRole('checkbox')).toBeNull());
    expect(screen.getByText('В набор данных')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Инструменты' })).toHaveAttribute(
      'href',
      '/admin/tools?provider=provider-1'
    );
  });
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import { collectionsApi } from '@shared/api/collections';
import { TemplateStatusModal } from './TemplateStatusModal';

vi.mock('@shared/lib/sse', () => ({
  openSSE: () => ({ disconnect: vi.fn() }),
}));

vi.mock('@shared/ui/Modal', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

it('fetches the server status graph while showing a fallback graph', async () => {
  const getGraph = vi
    .spyOn(collectionsApi, 'getTemplateStatusGraph')
    .mockResolvedValue({
      row_id: 'template-1',
      collection_id: 'collection-1',
      runtime_status: 'ready',
      stages: [
        { key: 'ready', label: 'Серверная готовность', state: 'completed' },
      ],
    });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <TemplateStatusModal
        collectionId="collection-1"
        row={{ id: 'template-1', title: 'Шаблон', runtime_status: 'ready' }}
        onClose={() => undefined}
      />
    </QueryClientProvider>
  );

  await waitFor(() =>
    expect(getGraph).toHaveBeenCalledWith('collection-1', 'template-1')
  );
  queryClient.clear();
});

it('shows template fields as a structured review instead of leaking raw schema JSON', async () => {
  vi.spyOn(collectionsApi, 'getTemplateStatusGraph').mockResolvedValue({
    row_id: 'template-1',
    collection_id: 'collection-1',
    runtime_status: 'approval_required',
    template_schema: {
      format: 'excel',
      fields: [
        {
          key: 'invoice.total',
          label: 'Итого',
          kind: 'scalar',
          type: 'number',
          required: true,
          locator: { token: '{{invoice.total}}' },
        },
      ],
    },
    stages: [{ key: 'approval', label: 'Утверждение', state: 'pending' }],
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const { container } = render(
    <QueryClientProvider client={queryClient}>
      <TemplateStatusModal
        collectionId="collection-1"
        row={{ id: 'template-1', title: 'Шаблон', runtime_status: 'approval_required' }}
        onClose={() => undefined}
      />
    </QueryClientProvider>
  );

  expect(await screen.findByText('Итого')).toBeTruthy();
  expect(screen.getByText('Обязательное')).toBeTruthy();
  expect(screen.getByText('Технические атрибуты')).toBeTruthy();
  expect(container.querySelector('pre')).toBeNull();
  expect(container.textContent).not.toContain('"fields"');
  queryClient.clear();
});

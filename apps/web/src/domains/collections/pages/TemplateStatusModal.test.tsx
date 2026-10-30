import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import { collectionsApi, type Collection } from '@shared/api/collections';
import { ApiError } from '@shared/api/errors';
import { TemplateStatusModal } from './TemplateStatusModal';

vi.mock('@shared/lib/sse', () => ({
  openSSE: () => ({ disconnect: vi.fn() }),
}));

vi.mock('@shared/ui/Modal', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@shared/ui/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

const readOnlyCollection = {
  id: 'collection-1',
  tenant_id: 'tenant-1',
  capabilities: {
    view_content: true,
    view_schema: true,
    can_edit_content: false,
    upload_documents: false,
    delete_documents: false,
    ingest: false,
    manage_memory: false,
    upload_csv: false,
    mutate_rows: false,
    reindex: false,
    upload_templates: false,
    analyze_templates: false,
    approve_templates: false,
    edit_templates: false,
    delete_templates: false,
    download: true,
  },
} as Collection;

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
        collection={readOnlyCollection}
        onPermissionDenied={async () => null}
        row={{ id: 'template-1', title: 'Шаблон', runtime_status: 'ready' }}
        onClose={() => undefined}
      />
    </QueryClientProvider>
  );

  await waitFor(() =>
    expect(getGraph).toHaveBeenCalledWith('collection-1', 'template-1', undefined)
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
        collection={readOnlyCollection}
        onPermissionDenied={async () => null}
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

it('keeps the edited description when the server revokes template access with 403', async () => {
  const onPermissionDenied = vi.fn().mockResolvedValue(null);
  const update = vi.spyOn(collectionsApi, 'updateTemplate').mockRejectedValue(
    new ApiError(403, 'Forbidden', 'Forbidden')
  );
  vi.spyOn(collectionsApi, 'getTemplateStatusGraph').mockResolvedValue({
    row_id: 'template-1',
    collection_id: 'collection-1',
    runtime_status: 'approval_required',
    description: 'Старое описание',
    stages: [{ key: 'approval', label: 'Утверждение', state: 'pending' }],
  });
  const editableCollection = {
    ...readOnlyCollection,
    capabilities: {
      ...readOnlyCollection.capabilities,
      can_edit_content: true,
      edit_templates: true,
      approve_templates: true,
    },
  } as Collection;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <TemplateStatusModal
        collectionId="collection-1"
        collection={editableCollection}
        onPermissionDenied={onPermissionDenied}
        row={{ id: 'template-1', title: 'Шаблон', runtime_status: 'approval_required', description: 'Старое описание' }}
        onClose={() => undefined}
      />
    </QueryClientProvider>
  );

  const description = await screen.findByLabelText('Описание шаблона');
  fireEvent.change(description, { target: { value: 'Мой черновик' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить описание' }));

  expect(await screen.findByText('Права изменились')).toBeInTheDocument();
  expect(description).toHaveValue('Мой черновик');
  expect(description).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Сохранить описание' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Согласовать шаблон' })).toBeDisabled();
  expect(update).toHaveBeenCalledWith('collection-1', 'template-1', { description: 'Мой черновик' }, undefined);
  expect(onPermissionDenied).toHaveBeenCalledOnce();
  queryClient.clear();
});

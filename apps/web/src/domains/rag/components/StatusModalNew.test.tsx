import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatusModalNew } from './StatusModalNew';

const apiRequestMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('@shared/ui/Modal', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@shared/ui/Toast', () => ({
  useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('@shared/api/http', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

vi.mock('@shared/lib/sse', () => ({
  openSSE: () => ({ disconnect: vi.fn() }),
}));

vi.mock('@shared/api/hooks/useDocumentStatus', () => ({
  useDocumentStatus: () => ({
    data: {
      stages: {},
      embed_models: [],
      index_models: [],
      ingest_policy: { controls: [], active_stages: [] },
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock('./PipelineView', () => ({
  PipelineView: () => <div data-testid="pipeline-view" />,
}));

vi.mock('./StageDetails', () => ({
  StageDetails: ({
    onDownloadOriginal,
    onDownloadNormalized,
  }: {
    onDownloadOriginal?: () => void;
    onDownloadNormalized?: () => void;
  }) => (
    <div>
      <button type="button" onClick={onDownloadOriginal}>Download Original</button>
      <button type="button" onClick={onDownloadNormalized}>Download Normalized</button>
    </div>
  ),
}));

function renderModal(props?: Partial<React.ComponentProps<typeof StatusModalNew>>) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <StatusModalNew docId="doc-123" onClose={() => undefined} {...props} />
    </QueryClientProvider>
  );
}

describe('StatusModalNew download behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses API download_url when downloadUrlPrefix is provided', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    apiRequestMock.mockResolvedValueOnce({ download_url: '/api/v1/files/ragdoc_doc-123_original/download' });

    renderModal({ downloadUrlPrefix: '/collections/1/docs/doc-123/download' });
    fireEvent.click(screen.getByRole('button', { name: /download original/i }));

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith('/collections/1/docs/doc-123/download?kind=original');
      expect(openSpy).toHaveBeenCalledWith('/api/v1/files/ragdoc_doc-123_original/download', '_blank', 'noopener,noreferrer');
    });
  });

  it('falls back to file_id endpoint when downloadUrlPrefix is not provided', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    renderModal();
    fireEvent.click(screen.getByRole('button', { name: /download normalized/i }));

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        expect.stringContaining('/files/ragdoc_doc-123_canonical/download'),
        '_blank',
        'noopener,noreferrer'
      );
    });
  });
});


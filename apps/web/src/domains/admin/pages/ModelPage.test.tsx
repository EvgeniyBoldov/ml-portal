import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  change: vi.fn(),
  type: 'embedding',
  selected: false,
  mode: 'edit',
  enabled: true,
}));
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: undefined }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock('@/shared/hooks/useEntityEditor', () => ({
  useEntityEditor: () => ({
    mode: mocks.mode,
    isNew: false,
    isEditable: mocks.mode === 'edit',
    isLoading: false,
    saving: false,
    entity: {
      id: 'model',
      name: 'Encoder',
      type: mocks.type,
      use_for_long_memory: mocks.selected,
      enabled: mocks.enabled,
    },
    formData: {
      type: mocks.type,
      use_for_long_memory: mocks.selected,
      enabled: mocks.enabled,
    },
    handleFieldChange: mocks.change,
  }),
}));
vi.mock('@/shared/ui', async original => ({
  ...(await original<typeof import('@/shared/ui')>()),
  useToast: () => ({ showToast: vi.fn() }),
}));
vi.mock('@/shared/ui/EntityPage', async original => ({
  ...(await original<typeof import('@/shared/ui/EntityPage')>()),
  EntityPageV2: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  Tab: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/shared/ui/GridLayout', async original => ({
  ...(await original<typeof import('@/shared/ui/GridLayout')>()),
  Block: ({
    fields,
    data,
    onChange,
  }: {
    fields?: { key: string; label: string }[];
    data?: Record<string, unknown>;
    onChange?: (key: string, value: unknown) => void;
  }) => (
    <div>
      {fields?.map(f =>
        f.key === 'enabled' ? (
          <output key={f.key} aria-label={f.label}>
            {String(data?.enabled)}
          </output>
        ) : f.key === 'use_for_long_memory' ? (
          <button key={f.key} onClick={() => onChange?.(f.key, true)}>
            {f.label}
          </button>
        ) : (
          <span key={f.key}>{f.label}</span>
        )
      )}
    </div>
  ),
}));
import { ModelPage } from './ModelPage';

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mocks.type = 'embedding';
  mocks.selected = false;
  mocks.mode = 'edit';
  mocks.enabled = true;
});

describe('LongMemory encoder selection', () => {
  it('shows vector dimensions and token limits for an encoder', () => {
    render(<ModelPage />);
    expect(screen.getByText('Размерность вектора')).toBeInTheDocument();
    expect(screen.getByText('Лимит текста (токены)')).toBeInTheDocument();
    expect(screen.queryByText('Векторы нормализованы')).not.toBeInTheDocument();
  });

  it('hides vector-only attributes for a reranker', () => {
    mocks.type = 'reranker';
    render(<ModelPage />);
    expect(screen.queryByText('Векторы нормализованы')).not.toBeInTheDocument();
    expect(screen.queryByText('Размерность вектора')).not.toBeInTheDocument();
    expect(
      screen.getByText('Лимит пары запрос/документ (токены)')
    ).toBeInTheDocument();
  });

  it('requires confirmation and cancellation does not change the selection', () => {
    render(<ModelPage />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Использовать для LongMemory' })
    );
    expect(
      screen.getByText(/длительная переиндексация всей LongMemory/)
    ).toBeInTheDocument();
    expect(mocks.change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(mocks.change).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', { name: 'Использовать для LongMemory' })
    );
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(mocks.change).toHaveBeenCalledWith('use_for_long_memory', true);
  });

  it('only offers this setting for embedding models', () => {
    mocks.type = 'llm_chat';
    render(<ModelPage />);
    expect(
      screen.queryByRole('button', { name: 'Использовать для LongMemory' })
    ).not.toBeInTheDocument();
  });
});

describe('Model enabled state', () => {
  it.each([
    ['view', true],
    ['view', false],
    ['edit', true],
    ['edit', false],
  ] as const)('preserves enabled in %s mode: %s', (mode, enabled) => {
    mocks.mode = mode;
    mocks.enabled = enabled;
    render(<ModelPage />);
    expect(screen.getByLabelText('Включена')).toHaveTextContent(
      String(enabled)
    );
  });
});

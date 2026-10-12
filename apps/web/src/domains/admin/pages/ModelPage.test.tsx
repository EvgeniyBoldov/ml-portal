import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ change: vi.fn(), type: 'embedding', selected: false }));
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined }) }));
vi.mock('@/shared/hooks/useEntityEditor', () => ({
  useEntityEditor: () => ({
    mode: 'edit', isNew: false, isEditable: true, isLoading: false, saving: false,
    entity: { id: 'model', name: 'Encoder', type: mocks.type, use_for_long_memory: mocks.selected },
    formData: { type: mocks.type, use_for_long_memory: mocks.selected },
    handleFieldChange: mocks.change,
  }),
}));
vi.mock('@/shared/ui', async (original) => ({
  ...await original<typeof import('@/shared/ui')>(), useToast: () => ({ showToast: vi.fn() }),
}));
vi.mock('@/shared/ui/EntityPage', async (original) => ({
  ...await original<typeof import('@/shared/ui/EntityPage')>(),
  EntityPageV2: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Tab: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/shared/ui/GridLayout', async (original) => ({
  ...await original<typeof import('@/shared/ui/GridLayout')>(),
  Block: ({ fields, onChange }: { fields?: { key: string; label: string }[]; onChange?: (key: string, value: unknown) => void }) => (
    <div>{fields?.filter((f) => f.key === 'use_for_long_memory').map((f) => (
      <button key={f.key} onClick={() => onChange?.(f.key, true)}>{f.label}</button>
    ))}</div>
  ),
}));
import { ModelPage } from './ModelPage';

afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); mocks.type = 'embedding'; mocks.selected = false; });

describe('LongMemory encoder selection', () => {
  it('requires confirmation and cancellation does not change the selection', () => {
    render(<ModelPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Использовать для LongMemory' }));
    expect(screen.getByText(/длительная переиндексация всей LongMemory/)).toBeInTheDocument();
    expect(mocks.change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(mocks.change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Использовать для LongMemory' }));
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(mocks.change).toHaveBeenCalledWith('use_for_long_memory', true);
  });

  it('only offers this setting for embedding models', () => {
    mocks.type = 'llm_chat';
    render(<ModelPage />);
    expect(screen.queryByRole('button', { name: 'Использовать для LongMemory' })).not.toBeInTheDocument();
  });
});

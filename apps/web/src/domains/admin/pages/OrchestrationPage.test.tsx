import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ saveRole: vi.fn(), saveLimits: vi.fn(), limitsQuery: vi.fn() }));
vi.mock('@/shared/api/hooks/useAdmin', () => ({ useModels: () => ({ data: { items: [] }, isLoading: false }) }));
vi.mock('@/shared/api/hooks/usePlatformSettings', () => {
  const roles = ['Planner', 'TurnPreflight', 'Synthesizer', 'FactExtractor', 'Memory', 'FactCompactor', 'DocumentMemoryExtractor'];
  return {
    ...Object.fromEntries(roles.flatMap((role) => [
      [`useActive${role}Role`, () => ({ data: { identity: 'Identity', mission: 'Mission', rules: 'Rules', safety: 'Safety', output_requirements: 'Output', examples: [], extras: {}, temperature: 0.2, model: 'model' }, isLoading: false })],
      [`useUpdate${role}Role`, () => ({ mutateAsync: mocks.saveRole, isPending: false })],
    ])),
    useOrchestratorExecutionLimits: (role: string) => {
      mocks.limitsQuery(role);
      return { data: { own: { llm_calls_max: 5, wall_time_ms_max: null }, effective: { llm_calls_max: 5, wall_time_ms_max: 300000 } }, isLoading: false };
    },
    useUpdateOrchestratorExecutionLimits: () => ({ mutateAsync: mocks.saveLimits, isPending: false }),
  };
});
vi.mock('@/shared/ui/ContractAwareEditor/ContractAwareEditor', () => ({
  ContractAwareEditor: ({ value }: { value: string }) => <span>{value}</span>,
}));
import { OrchestrationPage } from './OrchestrationPage';

afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); mocks.saveRole.mockResolvedValue({}); mocks.saveLimits.mockResolvedValue({}); });
const mount = () => render(<MemoryRouter><OrchestrationPage /></MemoryRouter>);

describe('Orchestrator settings applicability', () => {
  it('only exposes enforced actor limits and removes unused fields across all tabs', () => {
    mount();
    for (const title of ['Планировщик', 'Маршрутизатор запроса', 'Синтезатор ответа', 'Экстрактор фактов', 'Подбор контекста памяти', 'Нормализатор фактов', 'Изучатель документов']) {
      fireEvent.click(screen.getByRole('button', { name: title }));
      expect(screen.getByText('Параметры')).toBeInTheDocument();
      expect(screen.queryByText('Дополнительные параметры')).not.toBeInTheDocument();
      expect(screen.queryByText('Лимиты исполнения')).not.toBeInTheDocument();
      expect(Boolean(screen.queryByText('LLM-вызовы'))).toBe(['Планировщик', 'Синтезатор ответа'].includes(title));
      expect(Boolean(screen.queryByText('Политика отбора фактов'))).toBe(title === 'Экстрактор фактов');
      if (title === 'Планировщик') expect(screen.getByRole('heading', { name: 'Критерии ответа' })).toBeInTheDocument();
      if (title === 'Изучатель документов') expect(screen.queryByText('Примеры')).not.toBeInTheDocument();
    }
    expect(new Set(mocks.limitsQuery.mock.calls.map(([role]) => role))).toEqual(new Set(['planner', 'synthesizer']));
  });

  it('clearing a limit restores inheritance and keeps limit fields out of the role update', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[1], { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(mocks.saveLimits).toHaveBeenCalledWith({ llm_calls_max: null, wall_time_ms_max: null }));
    expect(mocks.saveRole.mock.calls[0][0]).not.toHaveProperty('llm_calls_max');
    expect(mocks.saveRole.mock.calls[0][0]).not.toHaveProperty('wall_time_ms_max');
  });
});

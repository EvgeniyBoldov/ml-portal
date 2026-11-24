import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ saveRole: vi.fn(), saveSettings: vi.fn(), fillDefaults: vi.fn(), limitsQuery: vi.fn() }));
vi.mock('@/shared/api/hooks/useAdmin', () => ({ useModels: () => ({ data: { items: [] }, isLoading: false }) }));
vi.mock('@/shared/api/hooks/usePlatformSettings', () => {
  const roles = {
    Planner: 'planner',
    TurnPreflight: 'turn_preflight',
    Synthesizer: 'synthesizer',
    FactExtractor: 'fact_extractor',
    Memory: 'memory',
    FactCompactor: 'fact_compactor',
    DocumentMemoryExtractor: 'document_memory_extractor',
  };
  return {
    ...Object.fromEntries(Object.entries(roles).flatMap(([role, roleType]) => [
      [`useActive${role}Role`, () => ({ data: { role_type: roleType, identity: 'Identity', mission: 'Mission', rules: 'Rules', safety: 'Safety', output_requirements: 'Output', examples: [], extras: {}, temperature: 0.2, model: 'model' }, isLoading: false })],
      [`useUpdate${role}Role`, () => ({ mutateAsync: mocks.saveRole, isPending: false })],
    ])),
    useOrchestratorExecutionLimits: (role: string) => {
      mocks.limitsQuery(role);
      return { data: { own: { llm_calls_max: 5, wall_time_ms_max: null }, effective: { llm_calls_max: 5, wall_time_ms_max: 300000 } }, isLoading: false };
    },
    useFillActivePromptDefaults: () => ({ mutate: mocks.fillDefaults, isPending: false }),
    useUpdateOrchestratorRoleSettings: () => ({ mutateAsync: mocks.saveSettings, isPending: false }),
  };
});
vi.mock('@/shared/ui/ContractAwareEditor/ContractAwareEditor', () => ({
  ContractAwareEditor: ({ value }: { value: string }) => <span>{value}</span>,
}));
import { OrchestrationPage } from './OrchestrationPage';

afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); mocks.saveRole.mockResolvedValue({}); mocks.saveSettings.mockResolvedValue({}); });
const mount = () => render(<MemoryRouter><OrchestrationPage /></MemoryRouter>);

describe('Orchestrator settings applicability', () => {
  it('shows stored phase limits on every active orchestrator tab', () => {
    mount();
    for (const title of ['Планировщик', 'Маршрутизатор запроса', 'Синтезатор ответа', 'Экстрактор фактов', 'Нормализатор фактов']) {
      fireEvent.click(screen.getByRole('button', { name: title }));
      expect(screen.getByText('Параметры')).toBeInTheDocument();
      expect(screen.queryByText('Дополнительные параметры')).not.toBeInTheDocument();
      expect(screen.queryByText('Лимиты исполнения')).not.toBeInTheDocument();
      expect(Boolean(screen.queryByText('LLM-вызовы'))).toBe(true);
      expect(Boolean(screen.queryByText('Таймаут фазы (мс)'))).toBe(true);
      expect(screen.queryByText('Время LLM-вызовов (мс)')).not.toBeInTheDocument();
      expect(Boolean(screen.queryByText('Политика отбора фактов'))).toBe(title === 'Экстрактор фактов');
      if (title === 'Планировщик') expect(screen.getByRole('heading', { name: 'Критерии ответа' })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'Подбор контекста памяти' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Изучатель документов' })).not.toBeInTheDocument();
    expect(new Set(mocks.limitsQuery.mock.calls.map(([role]) => role))).toEqual(new Set([
      'planner', 'turn_preflight', 'synthesizer', 'fact_extractor', 'fact_compactor',
    ]));
  });

  it('fills prompt defaults in the selected role from its tab header', () => {
    mount();
    for (const [title, role] of [
      ['Планировщик', 'planner'],
      ['Маршрутизатор запроса', 'turn_preflight'],
      ['Синтезатор ответа', 'synthesizer'],
      ['Экстрактор фактов', 'fact_extractor'],
    ]) {
      fireEvent.click(screen.getByRole('button', { name: title }));
      fireEvent.click(screen.getByRole('button', { name: 'Заполнить по дефолту' }));
      expect(mocks.fillDefaults).toHaveBeenLastCalledWith(role);

      fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
      expect(screen.queryByRole('button', { name: 'Заполнить по дефолту' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    }
    expect(mocks.fillDefaults).toHaveBeenCalledTimes(4);
    expect(mocks.saveSettings).not.toHaveBeenCalled();
  });

  it('matches the backend temperature range on every active role tab', () => {
    mount();
    for (const title of ['Планировщик', 'Маршрутизатор запроса', 'Синтезатор ответа', 'Экстрактор фактов', 'Нормализатор фактов']) {
      fireEvent.click(screen.getByRole('button', { name: title }));
      fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
      const temperature = screen.getByRole('spinbutton', { name: 'Temperature' });
      expect(temperature).toHaveAttribute('min', '0');
      expect(temperature).toHaveAttribute('max', '2');
      expect(temperature).toHaveAttribute('step', 'any');
      fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    }
  });

  it('saves role configuration and cleared limits atomically in one request', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[0], { target: { value: '0.5' } });
    fireEvent.change(inputs[1], { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(mocks.saveSettings).toHaveBeenCalledWith(expect.objectContaining({
      temperature: 0.5,
      execution_limits: { llm_calls_max: null, wall_time_ms_max: null },
    })));
    expect(mocks.saveRole).not.toHaveBeenCalled();
  });

  it('sends a cleared temperature as null to preserve the backend default', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Temperature' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(mocks.saveSettings.mock.calls[0][0]).toHaveProperty('temperature', null));
  });
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { expect, it, vi } from 'vitest';

import AgentRunsPage from './AgentRunsPage';
import ExternalRequestPage from './ExternalRequestPage';

const { getExternalRequest, listExternalRequests } = vi.hoisted(() => ({
  getExternalRequest: vi.fn().mockResolvedValue({
    run_id: 'run-1',
    source: 'clouds:express',
    status: 'completed',
    text: 'Проверить завтра и сообщить результат',
    user_name: 'Иван',
    created_at: '2026-11-27T09:00:00Z',
    updated_at: '2026-11-27T09:01:00Z',
    completed_at: '2026-11-27T09:01:00Z',
    timeline: [
      {
        id: 'accepted',
        kind: 'accepted',
        occurred_at: '2026-11-27T09:00:00Z',
        delivery_status: 'delivered',
        delivery_attempts: 1,
      },
      {
        id: 'timer',
        kind: 'waiting_timer',
        occurred_at: '2026-11-27T09:00:03Z',
        text: 'Проверка запланирована.',
        wake_at: '2026-11-27T09:00:15Z',
        resolved_at: '2026-11-27T09:00:15Z',
        delivery_status: 'delivered',
        delivery_attempts: 1,
      },
      {
        id: 'resumed',
        kind: 'timer_elapsed',
        occurred_at: '2026-11-27T09:00:15Z',
        delivery_attempts: 0,
      },
      {
        id: 'question',
        kind: 'waiting_confirmation',
        occurred_at: '2026-11-27T09:00:20Z',
        text: 'Продолжить проверку?',
        delivery_status: 'delivered',
        delivered_at: '2026-11-27T09:00:22Z',
        resolved_at: '2026-11-27T09:00:30Z',
        delivery_attempts: 1,
      },
      {
        id: 'answer',
        kind: 'answer',
        occurred_at: '2026-11-27T09:00:30Z',
        answer: false,
        delivery_attempts: 0,
      },
      {
        id: 'final',
        kind: 'completed',
        occurred_at: '2026-11-27T09:01:00Z',
        text: 'Проверка завершена.',
        delivery_status: 'pending',
        delivery_attempts: 0,
      },
    ],
  }),
  listExternalRequests: vi.fn().mockResolvedValue({
    total: 1,
    items: [
      {
        run_id: 'run-1',
        source: 'clouds:express',
        status: 'waiting_timer',
        text_preview: 'Проверить завтра',
        user_name: 'Иван',
        created_at: '2026-11-27T09:00:00Z',
        updated_at: '2026-11-27T09:01:00Z',
      },
    ],
  }),
}));

vi.mock('@/shared/api/admin', () => ({
  agentRunsApi: { list: vi.fn().mockResolvedValue([]) },
}));
vi.mock('@/shared/api/externalRequests', () => ({
  getExternalRequest,
  listExternalRequests,
}));

it('opens an assignment from its row and returns to the external requests tab', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter
        initialEntries={['/admin/agent-runs?tab=external-requests']}
      >
        <Routes>
          <Route path="/admin/agent-runs" element={<AgentRunsPage />} />
          <Route
            path="/admin/agent-runs/external-requests/:id"
            element={<ExternalRequestPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  expect(await screen.findByText('Проверить завтра')).toBeInTheDocument();
  expect(screen.getByText('clouds:express')).toBeInTheDocument();
  expect(screen.getByText('Ожидает по таймеру')).toBeInTheDocument();
  expect(listExternalRequests).toHaveBeenCalledWith(25, 0);
  expect(screen.getByRole('link', { name: 'run-1' })).toHaveAttribute(
    'href',
    '/admin/agent-runs/external-requests/run-1'
  );

  fireEvent.click(screen.getByText('Проверить завтра'));
  expect(
    screen.getByRole('heading', { name: 'Поручение' })
  ).toBeInTheDocument();
  expect(screen.getByText('run-1')).toBeInTheDocument();
  expect(
    await screen.findByText('Проверить завтра и сообщить результат')
  ).toBeInTheDocument();
  expect(getExternalRequest).toHaveBeenCalledWith('run-1');
  expect(
    screen.getByRole('heading', { name: 'Ход поручения' })
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Сведения о запросе' })
  ).toBeInTheDocument();
  expect(screen.getByText('Источник')).toBeInTheDocument();
  expect(screen.getByText('clouds:express')).toBeInTheDocument();
  expect(screen.getByText('1 мин 0 с')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Завершён');
  const timeline = within(
    screen.getByRole('list', { name: 'Сообщения и события поручения' })
  );
  const steps = timeline.getAllByRole('listitem');
  expect(
    steps.map(
      step => within(step).getByRole('heading', { level: 3 }).textContent
    )
  ).toEqual([
    'Входящее сообщение',
    'Поручение принято',
    'Промежуточный ответ',
    'Таймер сработал',
    'Запрос подтверждения',
    'Ответ пользователя',
    'Итоговый ответ',
  ]);
  expect(within(steps[0]).getByText('Иван')).toBeInTheDocument();
  expect(
    within(steps[2]).getByText('Проверка запланирована.')
  ).toBeInTheDocument();
  expect(within(steps[2]).getByText('Доставлено')).toBeInTheDocument();
  expect(within(steps[2]).getByText('Ожидание 12 с')).toBeInTheDocument();
  expect(screen.getByText(/задержка 2 с/)).toBeInTheDocument();
  expect(screen.getByText('Нет')).toBeInTheDocument();
  expect(screen.getByText('Ожидает доставки')).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole('button', { name: 'Назад: Внешние запросы' })
  );
  expect(await screen.findByText('Проверить завтра')).toBeInTheDocument();
});

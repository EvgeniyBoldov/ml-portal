import { fireEvent, render, screen, within } from '@testing-library/react';
import { ChatRunStatus } from './ChatRunStatus';

describe('ChatRunStatus', () => {
  it('shows the two latest safe stages and expands the bounded history', () => {
    render(
      <ChatRunStatus
        run={{
          userMessageId: 'user-1',
          assistantMessageId: 'assistant-1',
          status: 'running',
          progress: [
            {
              id: '1',
              runId: 'run-1',
              phase: 'planning',
              kind: 'start',
              description: 'Планирую ответ',
              createdAt: '2026-01-01T00:00:00Z',
            },
            {
              id: '2',
              runId: 'run-1',
              phase: 'execution',
              kind: 'agent_end',
              description: 'Собираю результат',
              createdAt: '2026-01-01T00:00:01Z',
            },
            {
              id: '3',
              runId: 'run-1',
              phase: 'execution',
              kind: 'agent_end',
              description: 'Формирую ответ',
              createdAt: '2026-01-01T00:00:02Z',
            },
          ],
        }}
      />
    );

    expect(screen.getByText('Собираю результат')).toBeInTheDocument();
    expect(screen.getByText('Формирую ответ')).toBeInTheDocument();
    expect(screen.queryByText('Планирую ответ')).not.toBeInTheDocument();
    expect(screen.queryByText('Сейчас')).not.toBeInTheDocument();
    expect(screen.queryByText('Перед этим')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Завершено')).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'Развернуть ход выполнения' })
    );
    expect(screen.getByText('Планирую ответ')).toBeInTheDocument();
  });

  it('shows only explicit outcomes, even when the previous stage has ended', () => {
    render(
      <ChatRunStatus
        run={{
          userMessageId: 'user-1',
          assistantMessageId: 'assistant-1',
          status: 'running',
          progress: [
            {
              id: '1',
              runId: 'run-1',
              phase: 'agent',
              kind: 'agent_end',
              description: 'Первый агент',
              createdAt: '',
            },
            {
              id: '2',
              runId: 'run-1',
              phase: 'agent',
              kind: 'agent_end',
              description: 'Второй агент',
              status: 'completed',
              createdAt: '',
            },
            {
              id: '3',
              runId: 'run-1',
              phase: 'agent',
              kind: 'agent_end',
              description: 'Третий агент',
              status: 'failed',
              createdAt: '',
            },
          ],
        }}
      />
    );
    expect(screen.getByLabelText('Завершено')).toBeInTheDocument();
    expect(screen.getByLabelText('Ошибка')).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', { name: 'Развернуть ход выполнения' })
    );
    const first = screen.getByText('Первый агент').closest('li')!;
    expect(within(first).queryByLabelText('Завершено')).not.toBeInTheDocument();
    expect(within(first).queryByLabelText('Ошибка')).not.toBeInTheDocument();
  });
});

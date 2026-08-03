import { fireEvent, render, screen } from '@testing-library/react';
import { ChatRunStatus } from './ChatRunStatus';

describe('ChatRunStatus', () => {
  it('shows the two latest safe stages and expands the bounded history', () => {
    render(
      <ChatRunStatus run={{
        userMessageId: 'user-1',
        assistantMessageId: 'assistant-1',
        status: 'running',
        progress: [
          { id: '1', runId: 'run-1', phase: 'planning', kind: 'start', description: 'Планирую ответ', createdAt: '2026-01-01T00:00:00Z' },
          { id: '2', runId: 'run-1', phase: 'execution', kind: 'agent_end', description: 'Собираю результат', createdAt: '2026-01-01T00:00:01Z' },
          { id: '3', runId: 'run-1', phase: 'execution', kind: 'agent_end', description: 'Формирую ответ', createdAt: '2026-01-01T00:00:02Z' },
        ],
      }} />,
    );

    expect(screen.getByText('Собираю результат')).toBeInTheDocument();
    expect(screen.getByText('Формирую ответ')).toBeInTheDocument();
    expect(screen.queryByText('Планирую ответ')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Развернуть ход выполнения' }));
    expect(screen.getByText('Планирую ответ')).toBeInTheDocument();
  });
});

import { fireEvent, render, screen } from '@testing-library/react';
import { ChatRunStatus } from './ChatRunStatus';

describe('ChatRunStatus', () => {
  it('shows the current safe progress and expands its history', () => {
    render(
      <ChatRunStatus run={{
        userMessageId: 'user-1',
        assistantMessageId: 'assistant-1',
        status: 'running',
        progress: [
          { id: '1', runId: 'run-1', phase: 'planning', kind: 'start', description: 'Планирую ответ', createdAt: '2026-01-01T00:00:00Z' },
          { id: '2', runId: 'run-1', phase: 'execution', kind: 'agent_end', description: 'Собираю результат', createdAt: '2026-01-01T00:00:01Z' },
        ],
      }} />,
    );

    expect(screen.getByText('Собираю результат')).toBeInTheDocument();
    expect(screen.queryByText('Планирую ответ')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подробности' }));
    expect(screen.getByText('Планирую ответ')).toBeInTheDocument();
  });
});

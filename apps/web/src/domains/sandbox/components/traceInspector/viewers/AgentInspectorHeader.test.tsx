import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TraceExecutorRun } from '../../../traceProjection';
import { AgentInspectorHeader } from './AgentInspectorHeader';

describe('AgentInspectorHeader', () => {
  it('keeps identity, status, and duration without a resource summary', () => {
    const executor = {
      executorName: 'Инвентаризация',
      accessSnapshot: { agentDescription: 'Проверяет состояние сети' },
      info: { status: 'completed', statusLabel: 'Готово', durationMs: 1250, statistics: [
        { key: 'tokens_total', label: 'Всего токенов', value: 150 },
      ] },
    } as TraceExecutorRun;
    render(<AgentInspectorHeader executor={executor} />);

    expect(screen.getByText('Инвентаризация')).toBeInTheDocument();
    expect(screen.getByText('Проверяет состояние сети')).toBeInTheDocument();
    expect(screen.getByText('Готово')).toBeInTheDocument();
    expect(screen.getByText('Время исполнения: 1.3 с')).toBeInTheDocument();
    expect(screen.queryByText('Ресурсы выполнения')).not.toBeInTheDocument();
    expect(screen.queryByText('Всего токенов')).not.toBeInTheDocument();
  });
});

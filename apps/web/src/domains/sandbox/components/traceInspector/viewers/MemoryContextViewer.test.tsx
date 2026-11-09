import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { memoryContextFromPayload } from '../../../traceProjection';
import { MemoryContextViewer } from './MemoryContextViewer';

describe('MemoryContextViewer', () => {
  it('shows separate scope groups and a clear unsuccessful-search state', () => {
    const context = memoryContextFromPayload({
      memory_owner: 'task',
      memory_owner_id: 'continued-task',
      memory_context: [
        {
          type: 'document_memory',
          groups: [
            {
              scope_slug: 'company',
              status: 'completed',
              count: 1,
              items: [
                {
                  scope_slug: 'company',
                  subject: 'Регламент',
                  text: 'Согласовать окно работ',
                },
              ],
            },
            {
              scope_slug: 'project',
              status: 'failed',
              count: 0,
              items: [],
              error: 'Индекс недоступен',
            },
          ],
        },
      ],
    });
    render(<MemoryContextViewer context={context} />);
    expect(
      screen.getByText('Контекст, доступный агенту при выполнении задачи.')
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Собственная накопленная память задания')
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Контекст подготовлен')).not.toBeInTheDocument();
    expect(screen.getByText('Память · company · 1')).toBeInTheDocument();
    expect(screen.getByText('Память · project · 0')).toBeInTheDocument();
    expect(screen.getByText('Согласовать окно работ')).toBeInTheDocument();
    expect(screen.getByText('Индекс недоступен')).toBeInTheDocument();
  });

  it('shows a large group as a short table with a readable full-group view', async () => {
    const items = Array.from({ length: 12 }, (_, index) => ({
      type: 'fact',
      scope: 'user',
      subject: `Факт ${index + 1}`,
      value: `Значение ${index + 1}`,
    }));
    const context = memoryContextFromPayload({ memory_context: items });
    render(<MemoryContextViewer context={context} />);

    expect(screen.getByText('Значение 1')).toBeInTheDocument();
    expect(screen.queryByText('Значение 12')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Показать ещё 2' }));
    expect(screen.getByText('Значение 12')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Свернуть список' })
    ).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Все записи (12)' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('uses a friendly label for the known current date fact and preserves its source key in details', async () => {
    const context = memoryContextFromPayload({
      memory_context: [
        {
          type: 'fact',
          scope: 'user',
          subject: 'current_date',
          value: '2026-11-08',
        },
      ],
    });
    render(<MemoryContextViewer context={context} />);
    expect(screen.getByText('Текущая дата')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Исходный ключ'));
    expect(screen.getByText('current_date')).toBeInTheDocument();
  });
});

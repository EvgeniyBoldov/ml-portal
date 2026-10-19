import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { memoryContextFromPayload } from '../../../traceProjection';
import { MemoryContextViewer } from './MemoryContextViewer';

describe('MemoryContextViewer', () => {
  it('shows the owner and separate scope groups, including an unsuccessful search', () => {
    const context = memoryContextFromPayload({
      memory_owner: 'task',
      memory_owner_id: 'continued-task',
      memory_context: [{
        type: 'document_memory',
        groups: [
          { scope_slug: 'company', status: 'completed', count: 1,
            items: [{ scope_slug: 'company', subject: 'Регламент', text: 'Согласовать окно работ' }] },
          { scope_slug: 'project', status: 'failed', count: 0, items: [], error: 'Индекс недоступен' },
        ],
      }],
    });
    render(<MemoryContextViewer context={context} />);
    expect(screen.getByText('Собственная накопленная память задания continued-task')).toBeInTheDocument();
    expect(screen.getByText('Память · company · 1')).toBeInTheDocument();
    expect(screen.getByText('Память · project · 0')).toBeInTheDocument();
    expect(screen.getByText('Согласовать окно работ')).toBeInTheDocument();
    expect(screen.getByText('Индекс недоступен')).toBeInTheDocument();
  });
});

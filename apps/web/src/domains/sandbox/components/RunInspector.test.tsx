import { render, screen } from '@testing-library/react';
import RunInspector from './RunInspector';
import type { RunStep } from '../hooks/useSandboxRun';

describe('RunInspector semantic trace', () => {
  it('renders semantic trace summary when trace event is provided', () => {
    const steps: RunStep[] = [
      {
        id: 'step-1',
        type: 'tool_call',
        data: { tool: 'collection.search', arguments: { query: 'netbox' } },
        timestamp: Date.now(),
      },
    ];

    render(
      <RunInspector
        steps={steps}
        selectedStepId="step-1"
        traceEvents={[
          {
            id: 'step-1',
            raw_type: 'operation_call',
            category: 'operation',
            title: 'Вызов операции',
            summary: 'collection.document.search',
            status: 'info',
            phase: 'operation',
            iteration: 1,
            raw: { id: 'step-1', raw_type: 'operation_call', raw: {} },
          },
        ]}
      />,
    );

    expect(screen.getByText(/Semantic Trace/)).toBeInTheDocument();
    expect(screen.getByText(/Category:/)).toBeInTheDocument();
    expect(screen.getAllByText(/operation/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Summary:/)).toBeInTheDocument();
    expect(screen.getByText(/collection.document.search/)).toBeInTheDocument();
  });
});

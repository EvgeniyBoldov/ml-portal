import { fireEvent, render, screen } from '@testing-library/react';
import RunInspector from './RunInspector';
import type { RunStep } from '../hooks/useSandboxRun';

describe('RunInspector semantic trace', () => {
  it('renders semantic trace summary when trace event is provided', { timeout: 15000 }, () => {
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

    fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
    expect(screen.getByText(/Semantic Trace/)).toBeInTheDocument();
    expect(screen.getByText(/Trace Artifacts/)).toBeInTheDocument();
    expect(screen.getByText(/Category:/)).toBeInTheDocument();
    expect(screen.getAllByText(/operation/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Summary:/)).toBeInTheDocument();
    expect(screen.getByText(/collection.document.search/)).toBeInTheDocument();
  });

  it('renders explicit empty state when no step selected', () => {
    render(<RunInspector steps={[]} selectedStepId={null} />);
    expect(screen.getByText(/No step selected/)).toBeInTheDocument();
    expect(screen.getByText(/Click a step in chat timeline to inspect details/)).toBeInTheDocument();
  });

  it('renders error tab with traceback payload when the step has runtime error data', () => {
    const steps: RunStep[] = [
      {
        id: 'step-err',
        type: 'status',
        data: {
          stage: 'sub_agent_unavailable',
          agent: 'net.enginer',
          error: 'Sub-agent net.enginer unavailable: Preflight failed',
          runtime_error_code: 'agent_precheck_failed',
          debug: {
            exception_type: 'ValidationError',
            traceback: 'Traceback (most recent call last):\n  File "/app/app/agents/operation_builder.py", line 196, in _build_single_operation\nValidationError: data_instance_id',
          },
        },
        timestamp: Date.now(),
      },
    ];

    render(<RunInspector steps={steps} selectedStepId="step-err" runStatus="error" />);

    fireEvent.click(screen.getByRole('button', { name: 'Error' }));
    expect(screen.getByText(/Error details/)).toBeInTheDocument();
    expect(screen.getAllByText(/agent_precheck_failed/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Traceback \(most recent call last\):/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ValidationError: data_instance_id/).length).toBeGreaterThan(0);
  });
});

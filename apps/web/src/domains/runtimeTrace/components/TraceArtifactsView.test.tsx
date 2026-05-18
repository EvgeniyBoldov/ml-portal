import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TraceArtifactsView } from './TraceArtifactsView';

describe('TraceArtifactsView', () => {
  it('renders extracted artifact sections', () => {
    render(
      <TraceArtifactsView
        artifacts={{
          prompt: 'You are planner',
          llmRequest: { model: 'gpt-x', payload: { goal: 'search' } },
          validation: { status: 'success' },
        }}
      />,
    );

    expect(screen.getByText('Prompt')).toBeInTheDocument();
    expect(screen.getByText('LLM Request')).toBeInTheDocument();
    expect(screen.getByText('Validation')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /View prompt/i }));
    expect(screen.getByText(/You are planner/)).toBeInTheDocument();
  });

  it('renders clear empty state when no artifacts are available', () => {
    render(<TraceArtifactsView artifacts={{}} />);
    expect(screen.getByText('No extracted artifacts')).toBeInTheDocument();
  });
});

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RawEventsViewer } from './RawEventsViewer';

describe('RawEventsViewer', () => {
  it('keeps payloads collapsed until an event is expanded', () => {
    render(<RawEventsViewer events={[{ sequence: 4, eventType: 'tool_result', value: { status: 'ok' } }]} />);

    expect(screen.getByText('#4')).toBeInTheDocument();
    expect(screen.getByText('tool_result')).toBeInTheDocument();
    expect(screen.getByText('ok')).not.toBeVisible();
  });

  it('filters matching event data and opens the complete payload in the JSON viewer', async () => {
    render(<RawEventsViewer events={[{ sequence: 5, eventType: 'agent_end', value: { outcome: 'fulfilled', answer: 'Found router' } }]} />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Поиск по событиям и данным' }), { target: { value: 'router' } });
    fireEvent.click(screen.getByText('agent_end'));
    expect(screen.getByText('Found router')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть полный payload' }));
    expect(await screen.findByText(/Событие #5 · agent_end/)).toBeInTheDocument();
    expect(screen.getByText('fulfilled')).toBeInTheDocument();
  });

  it('closes the full payload viewer when the inspector section changes', async () => {
    render(<RawEventsViewer events={[{ sequence: 8, eventType: 'tool_result', value: { answer: 'ready' } }]} />);
    fireEvent.click(screen.getByText('tool_result'));
    fireEvent.click(screen.getByRole('button', { name: 'Открыть полный payload' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent(document, new Event('agent-inspector-section-change'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

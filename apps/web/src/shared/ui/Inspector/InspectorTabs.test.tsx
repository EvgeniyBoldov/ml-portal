import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { InspectorTabs } from './InspectorTabs';

const tabs = [{ key: 'task', label: 'Задача' }, { key: 'result', label: 'Результат' }];

describe('InspectorTabs', () => {
  it('retains selection across updates for the same entity and notifies agent-only callers on tab changes', () => {
    const onChange = vi.fn();
    const view = render(<InspectorTabs entityId="agent-1" tabs={tabs} defaultTab="task" render={tab => <p>{tab} content</p>} onActiveTabChange={onChange} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Результат' }));
    expect(screen.getByRole('tab', { name: 'Результат' })).toHaveAttribute('aria-selected', 'true');
    expect(onChange).toHaveBeenCalledWith('result');

    view.rerender(<InspectorTabs entityId="agent-1" tabs={[...tabs]} defaultTab="task" render={tab => <p>{tab} updated content</p>} onActiveTabChange={onChange} />);
    expect(screen.getByRole('tab', { name: 'Результат' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('result updated content')).toBeInTheDocument();
  });
});

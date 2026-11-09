import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TraceToolOverrideSnapshot } from '../../../traceProjection';
import { ToolOverridesViewer } from './ToolOverridesViewer';

describe('ToolOverridesViewer', () => {
  it('keeps opaque configured operation keys collapsed while showing readable effective operations', () => {
    const id = '08deac7c-316e-4412-a322-9340f063cb8f';
    const snapshot: TraceToolOverrideSnapshot = {
      configuredPublication: { [id]: false },
      configuredSemantics: {},
      effectiveOperations: [{ toolId: id, operationSlug: 'inventory.search', operationName: 'Поиск инвентаря', publishedEffective: true }],
      suppressedPublication: [],
    };
    render(<ToolOverridesViewer snapshot={snapshot} />);

    expect(screen.getByText('Поиск инвентаря')).toBeInTheDocument();
    expect(screen.getByText('Доступна')).toBeInTheDocument();
    expect(screen.queryByText(id)).not.toBeInTheDocument();
    expect(screen.getByText('Показать технические настройки').closest('details')).not.toHaveAttribute('open');
  });
});

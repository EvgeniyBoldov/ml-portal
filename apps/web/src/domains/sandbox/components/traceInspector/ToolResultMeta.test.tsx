import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TraceToolResult } from '../../traceProjection';
import { ToolResultMeta } from './ToolResultMeta';

const result = (overrides: Partial<TraceToolResult>): TraceToolResult => ({
  data: undefined,
  summary: '',
  truncated: false,
  ...overrides,
});

describe('ToolResultMeta', () => {
  it.each([
    [50, 72, 'warn'],
    [92, 92, 'success'],
    [0, 50, 'danger'],
  ])('colours %s / %s from observed counts', (count, total, tone) => {
    render(
      <ToolResultMeta
        result={result({ returnedCount: count, sourceTotal: total })}
      />
    );
    expect(screen.getByText(`${count} / ${total}`).className).toContain(tone);
  });

  it('separates saved rows, received rows and source total', () => {
    render(
      <ToolResultMeta
        result={result({
          delivery: 'stored',
          receivedCount: 50,
          sourceTotal: 72,
        })}
        storedCount={49}
      />
    );
    expect(screen.getByText('50 / 72').className).toContain('warn');
    expect(screen.getByText('49 / 50').className).toContain('warn');
    expect(
      screen.getByText('Сохранено в Store / получено')
    ).toBeInTheDocument();
  });

  it('does not invent received count from stored rows', () => {
    render(
      <ToolResultMeta
        result={result({
          delivery: 'stored',
          returnedCount: 50,
          sourceTotal: 72,
        })}
      />
    );
    expect(screen.getByText('50 / 72')).toBeInTheDocument();
    expect(screen.getByText('50 / —')).toBeInTheDocument();
  });

  it('does not mark equal counts as complete if source reports partial coverage', () => {
    render(
      <ToolResultMeta
        result={result({
          returnedCount: 92,
          sourceTotal: 92,
          sourceComplete: false,
        })}
      />
    );
    expect(screen.getByText('92 / 92').className).toContain('warn');
  });
});

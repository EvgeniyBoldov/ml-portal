import { buildTraceDiagnostics } from './TraceDiagnosticsSummary';
import type { SemanticEvent } from '../types';

describe('buildTraceDiagnostics', () => {
  it('extracts runtime error contract fields', () => {
    const events: SemanticEvent[] = [
      {
        id: 'e1',
        raw_type: 'error',
        category: 'error',
        title: 'Ошибка',
        summary: 'fallback',
        status: 'error',
        phase: 'final',
        iteration: 0,
        raw: {
          id: 'e1',
          raw_type: 'error',
          raw: {
            runtime_error_code: 'budget_exceeded',
            runtime_error_message: 'Лимит исчерпан',
            operator_message: 'budget exhausted at planner loop',
          },
        },
      },
    ];

    const diagnostics = buildTraceDiagnostics(events);
    expect(diagnostics.runtimeErrors).toHaveLength(1);
    expect(diagnostics.runtimeErrors[0].code).toBe('budget_exceeded');
    expect(diagnostics.runtimeErrors[0].userMessage).toBe('Лимит исчерпан');
  });
});

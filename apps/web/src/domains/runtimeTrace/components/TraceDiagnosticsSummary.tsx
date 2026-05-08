import type { SemanticEvent } from '../types';

export interface TraceDiagnostics {
  budgetEvents: number;
  llmCalls: number;
  operationCalls: number;
  failedOperations: number;
  lastBudget: string;
  lastLlm: string;
  lastOperation: string;
}

export function buildTraceDiagnostics(events: SemanticEvent[]): TraceDiagnostics {
  const budget = events.filter((e) => e.category === 'budget');
  const llm = events.filter((e) => e.category === 'llm');
  const operations = events.filter((e) => e.category === 'operation');
  const failedOps = operations.filter((e) => e.status === 'error');
  return {
    budgetEvents: budget.length,
    llmCalls: llm.length,
    operationCalls: operations.length,
    failedOperations: failedOps.length,
    lastBudget: budget.length > 0 ? budget[budget.length - 1].summary : '—',
    lastLlm: llm.length > 0 ? llm[llm.length - 1].summary : '—',
    lastOperation: operations.length > 0 ? operations[operations.length - 1].summary : '—',
  };
}

export function TraceDiagnosticsInline({ diagnostics }: { diagnostics: TraceDiagnostics }) {
  return (
    <>
      budget {diagnostics.budgetEvents} · llm {diagnostics.llmCalls} · op {diagnostics.operationCalls} · fail {diagnostics.failedOperations}
    </>
  );
}

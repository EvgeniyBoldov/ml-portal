import type { SemanticEvent } from '../types';

export interface TraceDiagnostics {
  budgetEvents: number;
  llmCalls: number;
  operationCalls: number;
  failedOperations: number;
  lastBudget: string;
  lastLlm: string;
  lastOperation: string;
  runtimeErrors: Array<{
    code: string;
    userMessage: string;
    operatorMessage: string;
  }>;
}

export function buildTraceDiagnostics(events: SemanticEvent[]): TraceDiagnostics {
  const budget = events.filter((e) => e.category === 'budget');
  const llm = events.filter((e) => e.category === 'llm');
  const operations = events.filter((e) => e.category === 'operation');
  const failedOps = operations.filter((e) => e.status === 'error');
  const runtimeErrors = events
    .filter((e) => e.status === 'error' || e.category === 'error')
    .map((e) => {
      const raw = e.raw.raw || {};
      const code =
        String(raw.runtime_error_code ?? raw.code ?? 'runtime_error').trim() || 'runtime_error';
      const userMessage =
        String(raw.runtime_error_message ?? raw.user_message ?? raw.error ?? e.summary ?? 'Ошибка выполнения').trim();
      const operatorMessage =
        String(raw.operator_message ?? raw.error ?? raw.message ?? e.summary ?? '—').trim();
      return { code, userMessage, operatorMessage };
    });
  return {
    budgetEvents: budget.length,
    llmCalls: llm.length,
    operationCalls: operations.length,
    failedOperations: failedOps.length,
    lastBudget: budget.length > 0 ? budget[budget.length - 1].summary : '—',
    lastLlm: llm.length > 0 ? llm[llm.length - 1].summary : '—',
    lastOperation: operations.length > 0 ? operations[operations.length - 1].summary : '—',
    runtimeErrors,
  };
}

export function TraceDiagnosticsInline({ diagnostics }: { diagnostics: TraceDiagnostics }) {
  return (
    <>
      budget {diagnostics.budgetEvents} · llm {diagnostics.llmCalls} · op {diagnostics.operationCalls} · fail {diagnostics.failedOperations}
    </>
  );
}

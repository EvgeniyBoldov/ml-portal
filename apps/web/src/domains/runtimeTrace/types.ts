export type TraceCategory =
  | 'input'
  | 'budget'
  | 'llm'
  | 'decision'
  | 'retry'
  | 'operation'
  | 'policy'
  | 'planner'
  | 'final'
  | 'error'
  | 'system'
  | 'unknown';

export type TraceStatus = 'ok' | 'warn' | 'error' | 'info';

export interface RawEventRef {
  id: string;
  raw_type: string;
  raw: Record<string, unknown>;
}

export interface SemanticEvent {
  id: string;
  raw_type: string;
  category: TraceCategory;
  title: string;
  summary: string;
  status: TraceStatus;
  phase: string;
  iteration: number;
  started_at?: string;
  duration_ms?: number;
  inputs?: Record<string, unknown>;
  outputs?: Record<string, unknown>;
  decision?: Record<string, unknown>;
  budget?: Record<string, unknown>;
  refs?: Record<string, unknown>;
  raw: RawEventRef;
}

export interface TraceIteration {
  index: number;
  events: SemanticEvent[];
}

export interface RunTrace {
  iterations: TraceIteration[];
  total_events: number;
}

export interface TraceSourceStep {
  id: string;
  raw_type: string;
  data: Record<string, unknown>;
  step_number?: number;
  created_at?: string;
  duration_ms?: number;
}

import type { SemanticEvent } from './types';

const PHASE_ROUTED = new Set(['planner', 'agent', 'synthesis', 'triage', 'preflight', 'pipeline']);
const RUNTIME_NOISE = new Set(['delta', 'stop', 'done', 'run_paused']);
const TERMINAL_PLANNER_STEPS = new Set(['final', 'abort', 'ask_user', 'direct_answer']);

export function isPhaseRoutedEvent(event: SemanticEvent): boolean {
  return PHASE_ROUTED.has(event.phase);
}

export function isRuntimeNoiseStep(rawType: string): boolean {
  return RUNTIME_NOISE.has(rawType);
}

export function shouldCloseAgentWindowForPlannerStep(stepKind: string): boolean {
  return TERMINAL_PLANNER_STEPS.has(stepKind);
}

export function plannerStepToAgentWindowStatus(stepKind: string): 'ok' | 'warn' | 'error' {
  if (stepKind === 'final') return 'ok';
  if (stepKind === 'abort') return 'error';
  return 'warn';
}

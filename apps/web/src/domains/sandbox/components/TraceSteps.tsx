/**
 * TraceSteps — иерархический трейс через TraceTree (новая архитектура)
 *
 * Заменяет старую логику buildDisplaySteps на buildEntityTree + TraceTree.
 */

import * as React from 'react';
import { buildEntityTree } from '@/domains/runtimeTrace/buildEntityTree';
import { normalizeTraceEvent } from '@/domains/runtimeTrace/normalize';
import type { ContainerDebugRecord, TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../hooks/useSandboxRun';
import { TraceTree } from './TraceTree';
import styles from './TraceSteps.module.css';

interface TraceStepsProps {
  steps: RunStep[];
  isRunning: boolean;
  selectedEntityId: string | null;
  onSelectEntity: (entity: TraceEntity, steps: RunStep[]) => void;
}

function convertRunStepsToSemanticEvents(steps: RunStep[]) {
  return steps.map((step, index) =>
    normalizeTraceEvent({
      id: step.id,
      raw_type: step.type,
      data: step.data,
      step_number: step.orderNumber ?? index,
      created_at: new Date(step.timestamp).toISOString(),
      duration_ms: typeof step.data.duration_ms === 'number' ? step.data.duration_ms : undefined,
    })
  );
}

function isTraceDebugEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  const globalFlag = (window as Window & { __TRACE_DEBUG__?: boolean }).__TRACE_DEBUG__ === true;
  if (globalFlag) return true;
  try {
    return window.localStorage.getItem('trace_debug') === '1';
  } catch {
    return false;
  }
}

let lastDebugSignature = '';

export function TraceSteps({
  steps,
  isRunning,
  selectedEntityId,
  onSelectEntity,
}: TraceStepsProps): React.ReactElement | null {
  // Convert RunStep[] to TraceEntity tree
  const tree = React.useMemo(() => {
    if (steps.length === 0) return null;
    const events = convertRunStepsToSemanticEvents(steps);
    const debugRecords: ContainerDebugRecord[] = [];
    const treeResult = buildEntityTree(events, { debugRecords });
    const debugEnabled = isTraceDebugEnabled();
    if (debugEnabled) {
      const signature = `${steps.length}:${steps[steps.length - 1]?.id ?? 'none'}`;
      if (signature === lastDebugSignature) return treeResult;
      lastDebugSignature = signature;
      // eslint-disable-next-line no-console
      console.table(debugRecords);
    }
    return treeResult;
  }, [steps]);

  // Manage expanded state
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set());

  // Auto-expand on new tree
  React.useEffect(() => {
    if (tree && expandedIds.size === 0) {
      // Expand root and first level by default
      const newExpanded = new Set<string>([tree.id]);
      tree.children.forEach(child => newExpanded.add(child.id));
      setExpandedIds(newExpanded);
    }
  }, [tree]);

  const handleToggleExpand = React.useCallback((id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleSelect = React.useCallback((entity: TraceEntity) => {
    onSelectEntity(entity, steps);
  }, [onSelectEntity, steps]);

  if (!tree) {
    return isRunning ? (
      <div className={styles.empty}>Running...</div>
    ) : (
      <div className={styles.empty}>No steps</div>
    );
  }

  return (
    <div className={styles.container}>
      <TraceTree
        root={tree}
        selectedId={selectedEntityId}
        onSelect={handleSelect}
        expandedIds={expandedIds}
        onToggleExpand={handleToggleExpand}
      />
      {isRunning && (
        <div className={styles.runningIndicator}>
          <span className={styles.pulse} />
          <span>Running...</span>
        </div>
      )}
    </div>
  );
}

// Helper to find entity and related steps
export function findEntitySteps(entity: TraceEntity, allSteps: RunStep[]): RunStep[] {
  const eventIds = new Set(entity.sourceEventIds);
  return allSteps.filter(step => eventIds.has(step.id));
}

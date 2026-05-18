import * as React from 'react';
import { buildEntityTree } from '../buildEntityTree';
import { BudgetPills } from '../budget';
import type { SemanticEvent } from '../types';
import type { TraceEntity } from '../entityTypes';
import styles from './RuntimeTraceTree.module.css';

interface RuntimeTraceTreeProps {
  events: SemanticEvent[];
}

function statusLabel(status: TraceEntity['status']): string {
  if (status === 'ok') return 'OK';
  if (status === 'error') return 'Error';
  if (status === 'warn') return 'Warn';
  if (status === 'pending') return 'Pending';
  return 'Info';
}

function Row({
  entity,
  depth,
  expanded,
  onToggle,
}: {
  entity: TraceEntity;
  depth: number;
  expanded: Set<string>;
  onToggle: (id: string) => void;
}): React.ReactElement {
  const hasChildren = entity.children.length > 0;
  const isOpen = expanded.has(entity.id);
  const indent = { paddingLeft: `${12 + depth * 18}px` };

  return (
    <>
      <button type="button" className={styles.row} style={indent} onClick={() => hasChildren && onToggle(entity.id)}>
        <span>{hasChildren ? (isOpen ? '▾' : '▸') : '•'}</span>
        <span className={styles.title}>{entity.title}</span>
        {entity.durationMs != null && <span className={styles.meta}>{entity.durationMs}ms</span>}
        <BudgetPills
          used={entity.budget?.aggregated ?? entity.budget?.own}
          limits={entity.budget?.limits ?? null}
          metrics={['planner_steps', 'agent_steps', 'tool_calls', 'tokens_total', 'retries', 'wall_time_ms']}
        />
        <span className={styles.status}>{statusLabel(entity.status)}</span>
      </button>
      {hasChildren && isOpen && (
        <div className={styles.children}>
          {entity.children.map((child) => (
            <Row key={child.id} entity={child} depth={depth + 1} expanded={expanded} onToggle={onToggle} />
          ))}
        </div>
      )}
    </>
  );
}

export function RuntimeTraceTree({ events }: RuntimeTraceTreeProps): React.ReactElement {
  const tree = React.useMemo(() => buildEntityTree(events), [events]);
  const [expanded, setExpanded] = React.useState<Set<string>>(() => {
    const initial = new Set<string>([tree.id]);
    for (const child of tree.children) initial.add(child.id);
    return initial;
  });

  React.useEffect(() => {
    setExpanded((prev) => {
      if (prev.size > 0) return prev;
      const initial = new Set<string>([tree.id]);
      for (const child of tree.children) initial.add(child.id);
      return initial;
    });
  }, [tree]);

  const handleToggle = React.useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  if (!events.length) return <div className={styles.empty}>No trace events</div>;

  return (
    <div className={styles.container}>
      <Row entity={tree} depth={0} expanded={expanded} onToggle={handleToggle} />
    </div>
  );
}

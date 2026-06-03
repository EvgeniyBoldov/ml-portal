import {
  AgentInspectorTabs,
  InteractionInspectorTabs,
  OrchestratorInspectorTabs,
  PlannerInspectorTabs,
  RunInspectorTabs,
  UnknownInspectorTabs,
} from './kinds';
import type { SnapshotInspectorContentProps } from './snapshotTypes';

export function SnapshotEntityInspector({ entity, steps }: SnapshotInspectorContentProps) {
  if (entity.kind === 'run') {
    return <RunInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'planner') {
    return <PlannerInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'orchestrator') {
    return <OrchestratorInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'agent') {
    return <AgentInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'interaction') {
    return <InteractionInspectorTabs entity={entity} steps={steps} />;
  }
  return <UnknownInspectorTabs entity={entity} steps={steps} />;
}

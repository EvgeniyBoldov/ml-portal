import {
  AgentInspectorTabs,
  DialogInspectorTabs,
  ErrorInspectorTabs,
  InteractionInspectorTabs,
  LlmInspectorTabs,
  OrchestratorInspectorTabs,
  PlannerInspectorTabs,
  RunInspectorTabs,
  ToolInspectorTabs,
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
  if (entity.kind === 'llm') {
    return <LlmInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'tool') {
    return <ToolInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'error') {
    return <ErrorInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'dialog') {
    return <DialogInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'interaction') {
    return <InteractionInspectorTabs entity={entity} steps={steps} />;
  }
  return <UnknownInspectorTabs entity={entity} steps={steps} />;
}

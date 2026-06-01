import { InspectorEmpty, InspectorHeader, InspectorPanel } from '@/shared/ui/Inspector';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../hooks/useSandboxRun';
import {
  AgentInspectorTabs,
  ErrorInspectorTabs,
  LlmInspectorTabs,
  OrchestratorInspectorTabs,
  PlannerInspectorTabs,
  RunInspectorTabs,
  ToolInspectorTabs,
  UnknownInspectorTabs,
} from './entityInspector/index';
import { formatDuration, kindLabel, statusTone } from './entityInspector/index';

interface EntityInspectorProps {
  entity: TraceEntity | null;
  steps: RunStep[];
}

export function EntityInspector({ entity, steps }: EntityInspectorProps) {
  if (!entity) {
    return <InspectorEmpty message="Select a step to view details" />;
  }

  return (
    <InspectorPanel
      header={
        <InspectorHeader
          tone={statusTone(entity.status)}
          kindLabel={kindLabel(entity.kind)}
          title={entity.title}
          meta={formatDuration(entity.durationMs)}
        />
      }
    >
      {entity.kind === 'run' && <RunInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'phase' && <OrchestratorInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'agent' && <AgentInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'orchestrator' && <OrchestratorInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'llm' && <LlmInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'tool' && <ToolInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'planner' && <PlannerInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'error' && <ErrorInspectorTabs entity={entity} steps={steps} />}
      {entity.kind === 'unknown' && <UnknownInspectorTabs entity={entity} steps={steps} />}
    </InspectorPanel>
  );
}

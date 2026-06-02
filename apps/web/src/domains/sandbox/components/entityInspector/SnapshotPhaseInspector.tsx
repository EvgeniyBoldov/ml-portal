import {
  OrchestratorInspectorTabs,
  UnknownInspectorTabs,
} from './kinds';
import type { SnapshotInspectorContentProps } from './snapshotTypes';

export function SnapshotPhaseInspector({ entity, steps }: SnapshotInspectorContentProps) {
  if (entity.kind === 'phase') {
    return <OrchestratorInspectorTabs entity={entity} steps={steps} />;
  }
  return <UnknownInspectorTabs entity={entity} steps={steps} />;
}

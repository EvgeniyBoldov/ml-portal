import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../hooks/useSandboxRun';
import { SnapshotInspector } from './entityInspector/SnapshotInspector';

interface EntityInspectorProps {
  entity: TraceEntity | null;
  steps: RunStep[];
}

export function EntityInspector({ entity, steps }: EntityInspectorProps) {
  return <SnapshotInspector entity={entity} steps={steps} />;
}

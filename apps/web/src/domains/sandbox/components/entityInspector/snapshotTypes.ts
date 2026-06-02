import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../hooks/useSandboxRun';

export interface SnapshotInspectorContentProps {
  entity: TraceEntity;
  steps: RunStep[];
}

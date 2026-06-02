import { InspectorEmpty } from '@/shared/ui/Inspector';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import {
  getTraceEntityKindLabel,
  getTraceEntityTitle,
  getTraceSnapshotInspectorKind,
} from '@/domains/runtimeTrace/tracePresentation';
import type { RunStep } from '../../hooks/useSandboxRun';
import { BaseInspectorShell } from './BaseInspectorShell';
import { UnknownInspectorTabs } from './kinds';
import { SnapshotCallInspector } from './SnapshotCallInspector';
import { SnapshotEntityInspector } from './SnapshotEntityInspector';
import { SnapshotErrorInspector } from './SnapshotErrorInspector';
import { SnapshotPhaseInspector } from './SnapshotPhaseInspector';
import { formatDuration, statusTone } from './shared';
import { getSnapshotScopedSteps } from './snapshotSelectors';

interface SnapshotInspectorProps {
  entity: TraceEntity | null;
  steps: RunStep[];
}

function renderSnapshotContent(entity: TraceEntity, scopedSteps: RunStep[]) {
  const inspectorKind = getTraceSnapshotInspectorKind(entity);

  if (inspectorKind === 'phase') {
    return <SnapshotPhaseInspector entity={entity} steps={scopedSteps} />;
  }
  if (inspectorKind === 'call') {
    return <SnapshotCallInspector entity={entity} steps={scopedSteps} />;
  }
  if (inspectorKind === 'entity') {
    return <SnapshotEntityInspector entity={entity} steps={scopedSteps} />;
  }
  if (inspectorKind === 'error') {
    return <SnapshotErrorInspector entity={entity} steps={scopedSteps} />;
  }
  return <UnknownInspectorTabs entity={entity} steps={scopedSteps} />;
}

export function SnapshotInspector({ entity, steps }: SnapshotInspectorProps) {
  if (!entity) {
    return <InspectorEmpty message="Select a step to view details" />;
  }

  const scopedSteps = getSnapshotScopedSteps(entity, steps);

  return (
    <BaseInspectorShell
      tone={statusTone(entity.status)}
      kindLabel={getTraceEntityKindLabel(entity)}
      title={getTraceEntityTitle(entity)}
      meta={formatDuration(entity.durationMs)}
    >
      {renderSnapshotContent(entity, scopedSteps)}
    </BaseInspectorShell>
  );
}

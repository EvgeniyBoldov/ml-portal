import {
  ErrorInspectorTabs,
  UnknownInspectorTabs,
} from './kinds';
import type { SnapshotInspectorContentProps } from './snapshotTypes';

export function SnapshotErrorInspector({ entity, steps }: SnapshotInspectorContentProps) {
  if (entity.kind === 'error') {
    return <ErrorInspectorTabs entity={entity} steps={steps} />;
  }
  return <UnknownInspectorTabs entity={entity} steps={steps} />;
}

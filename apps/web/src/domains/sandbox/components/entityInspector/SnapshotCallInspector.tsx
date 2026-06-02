import {
  LlmInspectorTabs,
  ToolInspectorTabs,
  UnknownInspectorTabs,
} from './kinds';
import type { SnapshotInspectorContentProps } from './snapshotTypes';

export function SnapshotCallInspector({ entity, steps }: SnapshotInspectorContentProps) {
  if (entity.kind === 'llm') {
    return <LlmInspectorTabs entity={entity} steps={steps} />;
  }
  if (entity.kind === 'tool') {
    return <ToolInspectorTabs entity={entity} steps={steps} />;
  }
  return <UnknownInspectorTabs entity={entity} steps={steps} />;
}

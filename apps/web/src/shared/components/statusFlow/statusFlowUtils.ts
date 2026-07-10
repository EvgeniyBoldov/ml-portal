import type { FlowGraphModel, FlowNode, FlowSelection, FlowStatus } from './types';

const STATUS_PRIORITY: Record<FlowStatus, number> = {
  failed: 0,
  processing: 1,
  queued: 2,
  completed: 3,
  pending: 4,
};

export function getStatusTone(status: FlowStatus): 'neutral' | 'success' | 'warn' | 'danger' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'queued':
    case 'processing':
      return 'warn';
    case 'failed':
      return 'danger';
    default:
      return 'neutral';
  }
}

export function getStatusIcon(status: FlowStatus): string {
  switch (status) {
    case 'completed':
      return 'check';
    case 'queued':
    case 'processing':
      return 'loader';
    case 'failed':
      return 'x';
    default:
      return 'clock';
  }
}

export function getDisplayStatus(state?: string): FlowStatus {
  if (!state) return 'pending';
  switch (state) {
    case 'ok':
    case 'completed':
      return 'completed';
    case 'running':
    case 'processing':
      return 'processing';
    case 'error':
    case 'failed':
      return 'failed';
    case 'queued':
      return 'queued';
    default:
      return 'pending';
  }
}

function isActive(status: FlowStatus): boolean {
  return status === 'processing' || status === 'queued';
}

export function compareFlowNodePriority(a: FlowNode, b: FlowNode): number {
  const statusDelta = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
  if (statusDelta !== 0) return statusDelta;

  const aCompleted = a.finished_at ? new Date(a.finished_at).getTime() : -Infinity;
  const bCompleted = b.finished_at ? new Date(b.finished_at).getTime() : -Infinity;
  if (aCompleted !== bCompleted) return bCompleted - aCompleted;

  const aStarted = a.started_at ? new Date(a.started_at).getTime() : -Infinity;
  const bStarted = b.started_at ? new Date(b.started_at).getTime() : -Infinity;
  return bStarted - aStarted;
}

export function pickDefaultFlowSelection(model: FlowGraphModel): FlowSelection {
  const pipeline = model.pipeline ?? [];
  const laneItems: Array<FlowNode & { laneKey: string }> = (model.lanes ?? []).flatMap((lane) =>
    lane.items.map((item) => ({ ...item, laneKey: lane.key })),
  );

  const failedPipeline = pipeline.find((node) => node.status === 'failed');
  if (failedPipeline) return { nodeKey: failedPipeline.key };

  const failedLane = laneItems.find((node) => node.status === 'failed');
  if (failedLane) return { nodeKey: failedLane.key, laneKey: failedLane.laneKey, itemKey: failedLane.key };

  const activePipeline = [...pipeline].reverse().find((node) => isActive(node.status));
  if (activePipeline) return { nodeKey: activePipeline.key };

  const activeLane = laneItems.find((node) => isActive(node.status));
  if (activeLane) return { nodeKey: activeLane.key, laneKey: activeLane.laneKey, itemKey: activeLane.key };

  const completedCandidates = [...pipeline, ...laneItems]
    .filter((node) => node.status === 'completed')
    .sort(compareFlowNodePriority);
  const latestCompleted = completedCandidates[0];
  if (latestCompleted) {
      const laneKey = 'laneKey' in latestCompleted ? (latestCompleted as FlowNode & { laneKey: string }).laneKey : null;
      return {
        nodeKey: latestCompleted.key,
        laneKey,
        itemKey: latestCompleted.key,
      };
  }

  if (pipeline[0]) return { nodeKey: pipeline[0].key };
  const firstLane = model.lanes?.[0];
  const firstItem = firstLane?.items[0];
  return { nodeKey: firstItem?.key ?? null, laneKey: firstLane?.key ?? null, itemKey: firstItem?.key ?? null };
}

export function resolveSelectedNode(model: FlowGraphModel, selection: FlowSelection): {
  node: FlowNode | null;
  laneKey: string | null;
  stageType: 'pipeline' | 'lane';
} {
  if (!selection.nodeKey) {
    return { node: null, laneKey: null, stageType: 'pipeline' };
  }

  if (selection.laneKey) {
    const lane = model.lanes?.find((item) => item.key === selection.laneKey);
    const node = lane?.items.find((item) => item.key === (selection.itemKey || selection.nodeKey)) ?? null;
    return { node, laneKey: lane?.key ?? null, stageType: 'lane' };
  }

  const pipelineNode = model.pipeline.find((item) => item.key === selection.nodeKey) ?? null;
  if (pipelineNode) {
    return { node: pipelineNode, laneKey: null, stageType: 'pipeline' };
  }

  for (const lane of model.lanes ?? []) {
    const node = lane.items.find((item) => item.key === selection.nodeKey);
    if (node) return { node, laneKey: lane.key, stageType: 'lane' };
  }

  return { node: null, laneKey: null, stageType: 'pipeline' };
}

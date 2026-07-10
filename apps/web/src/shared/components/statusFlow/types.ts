export type FlowStatus = 'pending' | 'queued' | 'processing' | 'completed' | 'failed';

export interface FlowNode {
  key: string;
  label: string;
  status: FlowStatus;
  error?: string | null;
  metrics?: Record<string, unknown> | null;
  started_at?: string | null;
  finished_at?: string | null;
  version?: string | null;
  meta?: Record<string, unknown> | null;
}

export interface FlowLane {
  key: string;
  label: string;
  items: FlowNode[];
}

export interface FlowGraphModel {
  pipeline: FlowNode[];
  lanes?: FlowLane[];
}

export interface FlowSelection {
  nodeKey: string | null;
  laneKey?: string | null;
  itemKey?: string | null;
}

export interface FlowDetailAction {
  key: string;
  label: string;
  icon?: string;
  variant?: 'primary' | 'outline' | 'warning' | 'ghost';
  onClick: () => void;
}

export interface FlowDetailItem {
  label: string;
  value: string | number | boolean | string[];
}

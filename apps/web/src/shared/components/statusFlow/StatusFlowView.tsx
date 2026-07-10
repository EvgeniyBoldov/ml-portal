import React from 'react';

import { Icon } from '@shared/ui/Icon';

import type { FlowGraphModel, FlowNode, FlowSelection, FlowStatus } from './types';
import { getStatusIcon } from './statusFlowUtils';
import styles from './StatusFlowView.module.css';

const STATUS_COLORS: Record<FlowStatus, string> = {
  pending: 'var(--muted)',
  queued: 'var(--warning)',
  processing: 'var(--primary)',
  completed: 'var(--success)',
  failed: 'var(--danger)',
};

function FlowNodeButton({
  node,
  compact = false,
  isControlActive,
  isSelected,
  onClick,
}: {
  node: FlowNode;
  compact?: boolean;
  isControlActive: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
  const statusColor = STATUS_COLORS[node.status];
  const isActive = node.status === 'processing' || isControlActive;
  const className = compact ? styles.laneNode : styles.nodeButton;
  const iconClass = compact ? styles.laneIcon : styles.nodeIcon;
  const labelClass = compact ? styles.laneName : styles.nodeLabel;

  return (
    <button
      className={`${className} ${isSelected ? styles.selected : ''} ${isActive ? styles.active : ''} ${isControlActive ? styles.controlActive : ''}`}
      onClick={onClick}
      style={{ '--status-color': statusColor } as React.CSSProperties}
    >
      <div className={iconClass}>
        <Icon name={getStatusIcon(node.status)} size={compact ? 16 : 20} />
      </div>
      <div className={labelClass}>{node.label}</div>
      {!compact ? <div className={styles.nodeStatus}>{node.status}</div> : null}
    </button>
  );
}

function FlowConnector({ status }: { status: FlowStatus }) {
  const color = STATUS_COLORS[status];
  const isActive = status === 'processing';

  return (
    <div className={`${styles.connector} ${isActive ? styles.active : ''}`}>
      <svg width="40" height="2" viewBox="0 0 40 2">
        <line
          x1="0"
          y1="1"
          x2="40"
          y2="1"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={status === 'pending' ? '4 4' : 'none'}
        />
      </svg>
      {isActive ? <div className={styles.connectorPulse} style={{ background: color }} /> : null}
    </div>
  );
}

function FlowBranchConnector({
  count,
  statuses,
  fromStatus,
}: {
  count: number;
  statuses: FlowStatus[];
  fromStatus?: FlowStatus;
}) {
  if (count === 0) return null;

  if (count === 1) {
    const color = fromStatus === 'completed' ? STATUS_COLORS[statuses[0]] : STATUS_COLORS[fromStatus || 'pending'];
    return (
      <div className={styles.connector}>
        <svg width="40" height="2" viewBox="0 0 40 2">
          <line
            x1="0"
            y1="1"
            x2="40"
            y2="1"
            stroke={color}
            strokeWidth="2"
            strokeDasharray={statuses[0] === 'pending' ? '4 4' : 'none'}
          />
        </svg>
      </div>
    );
  }

  const itemHeight = 52;
  const gap = 8;
  const height = count * itemHeight + (count - 1) * gap;
  const midY = height / 2;

  return (
    <div className={styles.branchConnector}>
      <svg width="40" height={height} viewBox={`0 0 40 ${height}`}>
        {statuses.map((status, index) => {
          const y = index * (itemHeight + gap) + itemHeight / 2;
          const color = STATUS_COLORS[status];
          return (
            <g key={`${status}-${index}`}>
              <path
                d={`M 0 ${midY} C 20 ${midY} 20 ${y} 40 ${y}`}
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeDasharray={status === 'pending' ? '4 4' : 'none'}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function getConnectorStatus(from: FlowNode, to: FlowNode | undefined): FlowStatus {
  if (!to) return from.status;
  if (from.status === 'completed' && to.status !== 'pending') return to.status;
  if (from.status === 'completed') return 'completed';
  return from.status;
}

export function StatusFlowView({
  model,
  activeStageSlugs = [],
  selection,
  onSelect,
}: {
  model: FlowGraphModel;
  activeStageSlugs?: string[];
  selection: FlowSelection;
  onSelect: (selection: FlowSelection) => void;
}) {
  const activeSet = React.useMemo(() => new Set(activeStageSlugs), [activeStageSlugs]);
  const lanes = model.lanes ?? [];
  const maxItems = Math.max(...lanes.map((lane) => lane.items.length), 0);
  const showLanes = lanes.length > 0 && maxItems > 0;

  return (
    <div className={styles.pipeline}>
      <div className={styles.mainRow}>
        {model.pipeline.map((node, index) => (
          <React.Fragment key={node.key}>
            <FlowNodeButton
              node={node}
              isControlActive={activeSet.has(node.key)}
              isSelected={selection.nodeKey === node.key && !selection.laneKey}
              onClick={() => onSelect({ nodeKey: node.key, laneKey: null, itemKey: null })}
            />
            {index < model.pipeline.length - 1 ? <FlowConnector status={getConnectorStatus(node, model.pipeline[index + 1])} /> : null}
          </React.Fragment>
        ))}

        {showLanes ? (
          <>
            <FlowBranchConnector
              count={maxItems}
              statuses={Array.from({ length: maxItems }, (_, rowIndex) => {
                const rowStatuses = lanes
                  .map((lane) => lane.items[rowIndex]?.status)
                  .filter((status): status is FlowStatus => Boolean(status));
                return rowStatuses[0] ?? 'pending';
              })}
              fromStatus={model.pipeline[model.pipeline.length - 1]?.status}
            />
            <div className={styles.lanesWrapper}>
              <div
                className={styles.lanesHeader}
                style={{ gridTemplateColumns: lanes.map(() => 'minmax(120px, auto)').join(' 48px ') }}
              >
                {lanes.map((lane, index) => (
                  <React.Fragment key={lane.key}>
                    {index > 0 ? <div /> : null}
                    <div className={styles.laneHeaderCell}>{lane.label}</div>
                  </React.Fragment>
                ))}
              </div>
              <div
                className={styles.lanesGrid}
                style={{ gridTemplateColumns: lanes.map(() => 'minmax(120px, auto)').join(' 48px ') }}
              >
                {Array.from({ length: maxItems }).map((_, rowIndex) => (
                  <React.Fragment key={`row-${rowIndex}`}>
                    {lanes.map((lane, laneIndex) => {
                      const item = lane.items[rowIndex];
                      const prevLane = lanes[laneIndex - 1];
                      const prevItem = prevLane?.items[rowIndex];
                      return (
                        <React.Fragment key={`${lane.key}-${rowIndex}`}>
                          {laneIndex > 0 ? <FlowConnector status={prevItem?.status || 'pending'} /> : null}
                          {item ? (
                            <FlowNodeButton
                              node={item}
                              compact
                              isControlActive={activeSet.has(item.key)}
                              isSelected={selection.nodeKey === item.key && selection.laneKey === lane.key}
                              onClick={() => onSelect({ nodeKey: item.key, laneKey: lane.key, itemKey: item.key })}
                            />
                          ) : (
                            <div className={styles.laneNodePlaceholder} />
                          )}
                        </React.Fragment>
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </>
        ) : null}
      </div>

      <div className={styles.legend}>
        {(['pending', 'queued', 'processing', 'completed', 'failed'] as FlowStatus[]).map((status) => (
          <div key={status} className={styles.legendItem}>
            <div className={styles.legendDot} style={{ backgroundColor: STATUS_COLORS[status] }} />
            <span className={styles.legendLabel}>{status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default StatusFlowView;

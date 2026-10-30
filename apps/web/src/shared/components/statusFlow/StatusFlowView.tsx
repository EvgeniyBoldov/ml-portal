import React from 'react';

import { Icon } from '@shared/ui/Icon';
import { DocumentDAGView } from './DocumentDAGView';

import type {
  FlowGraphModel,
  FlowNode,
  FlowSelection,
  FlowStatus,
} from './types';
import { getStatusIcon, getStatusLabel } from './statusFlowUtils';
import styles from './StatusFlowView.module.css';

const STATUS_COLORS: Record<FlowStatus, string> = {
  pending: 'var(--muted)',
  queued: 'var(--warning)',
  processing: 'var(--primary)',
  completed: 'var(--success)',
  failed: 'var(--danger)',
  cancelled: 'var(--warning)',
  skipped: 'var(--muted)',
  unknown: 'var(--muted)',
};

function FlowNodeButton({
  node,
  isControlActive,
  isSelected,
  compact = false,
  onClick,
}: {
  node: FlowNode;
  isControlActive: boolean;
  isSelected: boolean;
  compact?: boolean;
  onClick: () => void;
}) {
  const statusColor = STATUS_COLORS[node.status];
  const isActive = node.status === 'processing' || isControlActive;
  const className = compact ? `${styles.nodeButton} ${styles.compactNodeButton}` : styles.nodeButton;
  const iconClass = compact ? `${styles.nodeIcon} ${styles.compactNodeIcon}` : styles.nodeIcon;
  const labelClass = styles.nodeLabel;

  return (
    <button
      className={`${className} ${isSelected ? styles.selected : ''} ${isActive ? styles.active : ''} ${isControlActive ? styles.controlActive : ''}`}
      aria-pressed={isSelected}
      aria-label={`${node.label}: ${getStatusLabel(node.status)}${isSelected ? ', выбран' : ''}`}
      onClick={onClick}
      style={{ '--status-color': statusColor } as React.CSSProperties}
    >
      <div className={`${iconClass} ${isActive ? styles.rotating : ''}`}>
        <Icon name={getStatusIcon(node.status)} size={20} />
      </div>
      <div className={labelClass} title={node.label}>
        {node.label}
      </div>
      <div className={styles.nodeStatus}>{getStatusLabel(node.status)}</div>
    </button>
  );
}

function FlowConnector({ status, compact = false }: { status: FlowStatus; compact?: boolean }) {
  const color = STATUS_COLORS[status];
  const isActive = status === 'processing';

  return (
    <div className={`${styles.connector} ${isActive ? styles.active : ''}`}>
      <svg width={compact ? 28 : 40} height="2" viewBox={`0 0 ${compact ? 28 : 40} 2`}>
        <line
          x1="0"
          y1="1"
          x2={compact ? 28 : 40}
          y2="1"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={status === 'pending' ? '4 4' : 'none'}
        />
      </svg>
      {isActive ? (
        <div className={styles.connectorPulse} style={{ background: color }} />
      ) : null}
    </div>
  );
}

function FlowBranchConnector({
  count,
  statuses,
  fromStatus,
  compact = false,
}: {
  count: number;
  statuses: FlowStatus[];
  fromStatus?: FlowStatus;
  compact?: boolean;
}) {
  if (count === 0) return null;

  if (count === 1) {
    const color =
      fromStatus === 'completed'
        ? STATUS_COLORS[statuses[0]]
        : STATUS_COLORS[fromStatus || 'pending'];
    return (
      <div className={styles.connector}>
        <svg width={compact ? 28 : 40} height="2" viewBox={`0 0 ${compact ? 28 : 40} 2`}>
          <line
            x1="0"
            y1="1"
            x2={compact ? 28 : 40}
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
      <svg width={compact ? 28 : 40} height={height} viewBox={`0 0 ${compact ? 28 : 40} ${height}`}>
        {statuses.map((status, index) => {
          const y = index * (itemHeight + gap) + itemHeight / 2;
          const color = STATUS_COLORS[status];
          return (
            <g key={`${status}-${index}`}>
              <path
                d={`M 0 ${midY} C ${compact ? 14 : 20} ${midY} ${compact ? 14 : 20} ${y} ${compact ? 28 : 40} ${y}`}
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

function getConnectorStatus(
  from: FlowNode,
  to: FlowNode | undefined
): FlowStatus {
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
  showLegend = true,
  compact = false,
}: {
  model: FlowGraphModel;
  showLegend?: boolean;
  /** Compact, locally scrollable pipeline used by the template status dialog. */
  compact?: boolean;
  activeStageSlugs?: string[];
  selection: FlowSelection;
  onSelect: (selection: FlowSelection) => void;
}) {
  const activeSet = React.useMemo(
    () => new Set(activeStageSlugs),
    [activeStageSlugs]
  );
  const lanes = model.lanes ?? [];
  const maxItems = Math.max(...lanes.map(lane => lane.items.length), 0);
  const showLanes = lanes.length > 0 && maxItems > 0;

  if (model.parallel) {
    return (
      <DocumentDAGView
        model={model}
        activeSet={activeSet}
        selection={selection}
        onSelect={onSelect}
        showLegend={showLegend}
      />
    );
  }

  return (
    <div className={`${styles.pipeline} ${compact ? styles.compactPipeline : ''}`}>
      <div
        className={compact ? styles.graphViewport : undefined}
        role={compact ? 'region' : undefined}
        aria-label={compact ? 'Этапы обработки шаблона' : undefined}
        tabIndex={compact ? 0 : undefined}
      >
      <div className={`${styles.mainRow} ${compact ? styles.compactMainRow : ''}`}>
        {model.pipeline.map((node, index) => (
          <React.Fragment key={node.key}>
            <FlowNodeButton
              node={node}
              isControlActive={activeSet.has(node.key)}
              isSelected={selection.nodeKey === node.key && !selection.laneKey}
              compact={compact}
              onClick={() =>
                onSelect({ nodeKey: node.key, laneKey: null, itemKey: null })
              }
            />
            {index < model.pipeline.length - 1 ? (
              <FlowConnector
                status={getConnectorStatus(node, model.pipeline[index + 1])}
                compact={compact}
              />
            ) : null}
          </React.Fragment>
        ))}

        {showLanes ? (
          <>
            <FlowBranchConnector
              count={maxItems}
              statuses={Array.from({ length: maxItems }, (_, rowIndex) => {
                const rowStatuses = lanes
                  .map(lane => lane.items[rowIndex]?.status)
                  .filter((status): status is FlowStatus => Boolean(status));
                return rowStatuses[0] ?? 'pending';
              })}
              fromStatus={model.pipeline[model.pipeline.length - 1]?.status}
              compact={compact}
            />
            <div className={styles.lanesWrapper}>
              <div
                className={styles.lanesHeader}
                style={{
                  gridTemplateColumns: lanes.map(() => '208px').join(' 48px '),
                }}
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
                style={{
                  gridTemplateColumns: lanes.map(() => '208px').join(' 48px '),
                }}
              >
                {Array.from({ length: maxItems }).map((_, rowIndex) => (
                  <React.Fragment key={`row-${rowIndex}`}>
                    {lanes.map((lane, laneIndex) => {
                      const item = lane.items[rowIndex];
                      const prevLane = lanes[laneIndex - 1];
                      const prevItem = prevLane?.items[rowIndex];
                      return (
                        <React.Fragment key={`${lane.key}-${rowIndex}`}>
                          {laneIndex > 0 ? (
                            <FlowConnector
                              status={prevItem?.status || 'pending'}
                              compact={compact}
                            />
                          ) : null}
                          {item ? (
                            <FlowNodeButton
                              node={item}
                              isControlActive={activeSet.has(item.key)}
                              compact={compact}
                              isSelected={
                                selection.nodeKey === item.key &&
                                selection.laneKey === lane.key
                              }
                              onClick={() =>
                                onSelect({
                                  nodeKey: item.key,
                                  laneKey: lane.key,
                                  itemKey: item.key,
                                })
                              }
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
      </div>

      {showLegend ? (
        <div className={styles.legend}>
          {(
            [
              'pending',
              'queued',
              'processing',
              'completed',
              'failed',
            ] as FlowStatus[]
          ).map(status => (
            <div key={status} className={styles.legendItem}>
              <div
                className={styles.legendDot}
                style={{ backgroundColor: STATUS_COLORS[status] }}
              />
              <span className={styles.legendLabel}>
                {getStatusLabel(status)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default StatusFlowView;

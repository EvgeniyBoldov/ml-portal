import React from 'react';

import { Icon } from '@shared/ui/Icon';

import { getStatusIcon, getStatusLabel } from './statusFlowUtils';
import type {
  FlowGraphModel,
  FlowLane,
  FlowNode,
  FlowSelection,
  FlowStatus,
} from './types';
import styles from './DocumentDAGView.module.css';

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

interface PositionedEdge {
  key: string;
  d: string;
  color: string;
  active: boolean;
  dashed: boolean;
}

interface Edge {
  from: string;
  to: string;
  status: FlowStatus;
}

interface NodeBounds {
  left: number;
  right: number;
  top: number;
  height: number;
}

const EMPTY_NODES: FlowNode[] = [];
const EMPTY_LANES: FlowLane[] = [];

function NodeCard({
  node,
  renderKey,
  selected,
  controlActive,
  onClick,
}: {
  node: FlowNode;
  renderKey: string;
  selected: boolean;
  controlActive: boolean;
  onClick: () => void;
}) {
  const isActive = node.status === 'processing' || controlActive;
  return (
    <button
      type="button"
      data-flow-node={renderKey}
      className={`${styles.node} ${selected ? styles.selected : ''} ${controlActive ? styles.controlActive : ''}`}
      style={
        { '--status-color': STATUS_COLORS[node.status] } as React.CSSProperties
      }
      title={node.label}
      aria-label={`${node.label}: ${getStatusLabel(node.status)}`}
      aria-pressed={selected}
      onClick={onClick}
    >
      <span
        className={`${styles.statusIcon} ${isActive ? styles.rotating : ''}`}
        aria-hidden="true"
      >
        <Icon name={getStatusIcon(node.status)} size={20} />
      </span>
      <span className={styles.nodeLabel}>{node.label}</span>
      <span className={styles.nodeStatus}>{getStatusLabel(node.status)}</span>
    </button>
  );
}

function laneNode(lane: FlowLane): FlowNode | undefined {
  return lane.items[0];
}

function connectorStatus(from: FlowStatus, to: FlowStatus): FlowStatus {
  if (from !== 'completed') return from;
  return to === 'pending' ? 'completed' : to;
}

function positionedEdges(
  canvas: HTMLDivElement,
  edges: Edge[]
): { width: number; height: number; paths: PositionedEdge[] } {
  const bounds = canvas.getBoundingClientRect();
  const rects = new Map<string, NodeBounds>();
  canvas.querySelectorAll<HTMLElement>('[data-flow-node]').forEach(element => {
    if (element.dataset.flowNode)
      rects.set(element.dataset.flowNode, element.getBoundingClientRect());
  });
  const valid = edges.flatMap(edge => {
    const from = rects.get(edge.from);
    const to = rects.get(edge.to);
    return from && to ? [{ edge, from, to }] : [];
  });
  const bySource = new Map<string, typeof valid>();
  valid.forEach(item =>
    bySource.set(item.edge.from, [
      ...(bySource.get(item.edge.from) ?? []),
      item,
    ])
  );
  const paths: PositionedEdge[] = [];

  bySource.forEach(items => {
    const first = items[0];
    const sx = first.from.right - bounds.left;
    const sy = first.from.top + first.from.height / 2 - bounds.top;
    const targets = items.map(item => ({
      ...item,
      tx: item.to.left - bounds.left,
      ty: item.to.top + item.to.height / 2 - bounds.top,
    }));
    const isFork = targets.length > 1 || Math.abs(targets[0].ty - sy) > 1;
    if (!isFork) {
      paths.push({
        key: `${items[0].edge.from}-${items[0].edge.to}`,
        d: `M ${sx} ${sy} H ${targets[0].tx}`,
        color: STATUS_COLORS[items[0].edge.status],
        active: items[0].edge.status === 'processing',
        dashed: items[0].edge.status === 'pending',
      });
      return;
    }

    const nearestTargetX = Math.min(...targets.map(target => target.tx));
    const splitX = sx + Math.max(0, (nearestTargetX - sx) / 2);
    const bends = targets.map(target => {
      const verticalDirection = Math.sign(target.ty - sy);
      const radius = Math.min(5, Math.abs(target.ty - sy) / 2);
      return {
        target,
        radius,
        elbowY: target.ty - verticalDirection * radius,
      };
    });
    const minY = Math.min(sy, ...bends.map(bend => bend.elbowY));
    const maxY = Math.max(sy, ...bends.map(bend => bend.elbowY));
    paths.push({
      key: `${items[0].edge.from}-stem`,
      d: `M ${sx} ${sy} H ${splitX}${maxY !== minY ? ` M ${splitX} ${minY} V ${maxY}` : ''}`,
      color: STATUS_COLORS[first.edge.status],
      active: first.edge.status === 'processing',
      dashed: first.edge.status === 'pending',
    });
    bends.forEach(({ target, radius, elbowY }) => {
      const d =
        Math.abs(target.ty - sy) < 1
          ? `M ${splitX} ${sy} H ${target.tx}`
          : `M ${splitX} ${elbowY} Q ${splitX} ${target.ty} ${splitX + radius} ${target.ty} H ${target.tx}`;
      paths.push({
        key: `${target.edge.from}-${target.edge.to}`,
        d,
        color: STATUS_COLORS[target.edge.status],
        active: target.edge.status === 'processing',
        dashed: target.edge.status === 'pending',
      });
    });
  });
  return { width: canvas.scrollWidth, height: canvas.scrollHeight, paths };
}

export function DocumentDAGView({
  model,
  activeSet,
  selection,
  onSelect,
  showLegend,
}: {
  model: FlowGraphModel;
  activeSet: Set<string>;
  selection: FlowSelection;
  onSelect: (selection: FlowSelection) => void;
  showLegend: boolean;
}) {
  const canvasRef = React.useRef<HTMLDivElement>(null);
  const [geometry, setGeometry] = React.useState({
    width: 0,
    height: 0,
    paths: [] as PositionedEdge[],
  });
  const lanes = model.lanes ?? EMPTY_LANES;
  const embeddingLane = lanes.find(lane => lane.key === 'embedding');
  const indexLane = lanes.find(lane => lane.key === 'index');
  const memoryLanes = React.useMemo(
    () => lanes.filter(lane => model.parallel?.laneKeys.includes(lane.key)),
    [lanes, model.parallel]
  );
  const knowledgeLane =
    memoryLanes.find(lane => lane.key.endsWith('.knowledge')) ?? memoryLanes[0];
  const graphLane =
    memoryLanes.find(lane => lane.key.endsWith('.graph')) ?? memoryLanes[1];
  const preNodes = React.useMemo(
    () => model.pipeline.filter(node => node.key !== 'chunk'),
    [model.pipeline]
  );
  const chunkNode = model.pipeline.find(node => node.key === 'chunk');
  const embeddings = embeddingLane?.items ?? EMPTY_NODES;
  const indexes = indexLane?.items ?? EMPTY_NODES;
  const branchCount = Math.max(embeddings.length, indexes.length);
  const knowledge = knowledgeLane ? laneNode(knowledgeLane) : undefined;
  const graph = graphLane ? laneNode(graphLane) : undefined;
  const memoryNodes = React.useMemo(
    () => [knowledge, graph].filter((node): node is FlowNode => Boolean(node)),
    [knowledge, graph]
  );
  const edges = React.useMemo(() => {
    const result: Edge[] = [];
    preNodes.forEach((node, index) => {
      const next = preNodes[index + 1];
      if (next)
        result.push({
          from: node.key,
          to: next.key,
          status: connectorStatus(node.status, next.status),
        });
    });
    const normalize = preNodes.find(node => node.key === model.parallel?.after);
    if (normalize && chunkNode)
      result.push({
        from: normalize.key,
        to: 'rag:chunk',
        status: connectorStatus(normalize.status, chunkNode.status),
      });
    if (normalize && knowledge && knowledgeLane)
      result.push({
        from: normalize.key,
        to: knowledgeLane.key,
        status: connectorStatus(normalize.status, knowledge.status),
      });
    if (chunkNode) {
      for (let index = 0; index < branchCount; index += 1) {
        const embedding = embeddings[index];
        const itemIndex = indexes[index];
        if (embedding)
          result.push({
            from: 'rag:chunk',
            to: `rag:embedding:${index}`,
            status: connectorStatus(chunkNode.status, embedding.status),
          });
        else if (itemIndex)
          result.push({
            from: 'rag:chunk',
            to: `rag:index:${index}`,
            status: connectorStatus(chunkNode.status, itemIndex.status),
          });
        if (embedding && itemIndex)
          result.push({
            from: `rag:embedding:${index}`,
            to: `rag:index:${index}`,
            status: connectorStatus(embedding.status, itemIndex.status),
          });
      }
    }
    if (knowledge && graph && knowledgeLane && graphLane)
      result.push({
        from: knowledgeLane.key,
        to: graphLane.key,
        status: connectorStatus(knowledge.status, graph.status),
      });
    return result;
  }, [
    preNodes,
    model.parallel,
    chunkNode,
    knowledge,
    knowledgeLane,
    embeddings,
    indexes,
    branchCount,
    graph,
    graphLane,
  ]);

  React.useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const update = () => setGeometry(positionedEdges(canvas, edges));
    update();
    const ResizeObserverConstructor = window.ResizeObserver;
    if (!ResizeObserverConstructor) return undefined;
    const observer = new ResizeObserverConstructor(update);
    observer.observe(canvas);
    canvas
      .querySelectorAll('[data-flow-node]')
      .forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, [edges, model]);

  const renderCard = (node: FlowNode, renderKey: string, laneKey?: string) => (
    <NodeCard
      key={renderKey}
      node={node}
      renderKey={renderKey}
      selected={
        selection.nodeKey === node.key &&
        (laneKey ? selection.laneKey === laneKey : !selection.laneKey)
      }
      controlActive={activeSet.has(node.key)}
      onClick={() =>
        onSelect({
          nodeKey: node.key,
          laneKey: laneKey ?? null,
          itemKey: laneKey ? node.key : null,
        })
      }
    />
  );

  return (
    <div className={styles.viewport}>
      <div className={styles.canvas} ref={canvasRef}>
        <svg
          className={styles.connections}
          width={geometry.width}
          height={geometry.height}
          aria-hidden="true"
        >
          {geometry.paths.map(path => (
            <path
              key={path.key}
              d={path.d}
              fill="none"
              stroke={path.color}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`${path.active ? styles.edgeActive : ''} ${path.dashed ? styles.edgePending : ''}`}
            />
          ))}
        </svg>
        <section
          className={`${styles.group} ${styles.preprocessing}`}
          aria-label="Предобработка"
        >
          <h3 className={styles.groupTitle}>ПРЕДОБРАБОТКА</h3>
          <div className={styles.preprocessingRow}>
            {preNodes.map(node => renderCard(node, node.key))}
          </div>
        </section>
        <div className={styles.branches}>
          <section className={`${styles.group} ${styles.rag}`} aria-label="RAG">
            <h3 className={styles.groupTitle}>RAG</h3>
            <div className={styles.ragFlow}>
              {chunkNode ? (
                <div className={styles.chunk}>
                  {renderCard(chunkNode, 'rag:chunk')}
                </div>
              ) : null}
              {branchCount > 0 ? (
                <div className={styles.ragBranches}>
                  <div className={styles.branchRows}>
                    {Array.from({ length: branchCount }, (_, index) => (
                      <div className={styles.branchRow} key={`branch-${index}`}>
                        {embeddings[index] && embeddingLane ? (
                          renderCard(
                            embeddings[index],
                            `rag:embedding:${index}`,
                            embeddingLane.key
                          )
                        ) : (
                          <span className={styles.emptyCard} />
                        )}
                        {indexes[index] && indexLane ? (
                          renderCard(
                            indexes[index],
                            `rag:index:${index}`,
                            indexLane.key
                          )
                        ) : (
                          <span className={styles.emptyCard} />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </section>
          <section
            className={`${styles.group} ${styles.longMemory}`}
            aria-label="LongMemory"
          >
            <h3 className={styles.groupTitle}>LongMemory</h3>
            <div className={styles.memoryFlow}>
              {memoryNodes.map((node, index) => {
                const lane = memoryLanes.find(
                  item => item.items[0]?.key === node.key
                );
                return lane ? (
                  renderCard(node, lane.key, lane.key)
                ) : (
                  <React.Fragment key={`memory-${index}`} />
                );
              })}
            </div>
          </section>
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
                <span
                  className={styles.legendDot}
                  style={{ backgroundColor: STATUS_COLORS[status] }}
                />
                <span>{getStatusLabel(status)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

import React from 'react';
import { Icon } from '@shared/ui/Icon';
import styles from './PipelineView.module.css';

export type PipelineStageStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'queued';

export interface PipelineStage {
  key: string;
  label: string;
  status: PipelineStageStatus;
  error?: string | null;
  metrics?: Record<string, any> | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface EmbeddingModel {
  model: string;
  status: PipelineStageStatus;
  version?: string | null;
  error?: string | null;
  metrics?: Record<string, any> | null;
  started_at?: string | null;
  finished_at?: string | null;
}

interface PipelineViewProps {
  stages: PipelineStage[];
  embeddings: EmbeddingModel[];
  indexes: EmbeddingModel[];
  activeStageSlugs?: string[];
  selectedStage: string | null;
  selectedModel: string | null;
  onSelectStage: (stage: string | null, model?: string | null) => void;
}

const STATUS_ICONS: Record<PipelineStageStatus, string> = {
  pending: 'clock',
  queued: 'clock',
  processing: 'loader',
  completed: 'check',
  failed: 'x',
};

const STATUS_COLORS: Record<PipelineStageStatus, string> = {
  pending: 'var(--muted)',
  queued: 'var(--warning)',
  processing: 'var(--primary)',
  completed: 'var(--success)',
  failed: 'var(--danger)',
};

function StageNode({
  stage,
  stageSlug,
  isControlActive,
  isSelected,
  onClick,
}: {
  stage: PipelineStage;
  stageSlug: string;
  isControlActive: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
  const statusColor = STATUS_COLORS[stage.status];
  const isActive = stage.status === 'processing' || isControlActive;

  return (
    <button
      className={`${styles.stageNode} ${isSelected ? styles.selected : ''} ${isActive ? styles.active : ''} ${isControlActive ? styles.controlActive : ''}`}
      onClick={onClick}
      data-stage={stageSlug}
      style={{ '--status-color': statusColor } as React.CSSProperties}
    >
      <div className={styles.stageIcon}>
        <Icon name={STATUS_ICONS[stage.status]} size={20} />
      </div>
      <div className={styles.stageLabel}>{stage.label}</div>
      <div className={styles.stageStatus}>{stage.status}</div>
    </button>
  );
}

function ModelNode({
  model,
  type,
  isControlActive,
  isSelected,
  onClick,
}: {
  model: EmbeddingModel;
  type: 'embed' | 'index';
  isControlActive: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
  const statusColor = STATUS_COLORS[model.status];
  const isActive = model.status === 'processing' || isControlActive;
  const shortName = model.model.replace('embed.', '').replace('index.', '');

  return (
    <button
      className={`${styles.modelNode} ${isSelected ? styles.selected : ''} ${isActive ? styles.active : ''} ${isControlActive ? styles.controlActive : ''}`}
      onClick={onClick}
      style={{ '--status-color': statusColor } as React.CSSProperties}
    >
      <div className={styles.modelIcon}>
        <Icon name={STATUS_ICONS[model.status]} size={16} />
      </div>
      <div className={styles.modelName}>{shortName}</div>
    </button>
  );
}

function Connector({ status }: { status: PipelineStageStatus }) {
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
      {isActive && <div className={styles.connectorPulse} style={{ background: color }} />}
    </div>
  );
}

function BranchConnector({
  count,
  statuses,
  fromStatus,
}: {
  count: number;
  statuses: PipelineStageStatus[];
  fromStatus?: PipelineStageStatus;
}) {
  if (count === 0) return null;

  // Simple horizontal connector for single model
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

  // Branching connector for multiple models
  const itemHeight = 52;
  const gap = 8;
  const height = count * itemHeight + (count - 1) * gap;
  const midY = height / 2;

  return (
    <div className={styles.branchConnector}>
      <svg width="40" height={height} viewBox={`0 0 40 ${height}`}>
        {statuses.map((status, i) => {
          const y = i * (itemHeight + gap) + itemHeight / 2;
          const color = STATUS_COLORS[status];
          return (
            <g key={i}>
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

export function PipelineView({
  stages,
  embeddings,
  indexes,
  activeStageSlugs = [],
  selectedStage,
  selectedModel,
  onSelectStage,
}: PipelineViewProps) {
  const activeSet = React.useMemo(() => new Set(activeStageSlugs), [activeStageSlugs]);

  // Get main pipeline stages (upload, extract, normalize, chunk)
  const mainStages = stages.filter(s => 
    ['upload', 'extract', 'normalize', 'chunk'].includes(s.key)
  );

  // Determine overall status for connectors
  const getConnectorStatus = (fromIndex: number): PipelineStageStatus => {
    const from = mainStages[fromIndex];
    const to = mainStages[fromIndex + 1];
    if (!from || !to) return 'pending';
    if (from.status === 'completed' && to.status !== 'pending') return to.status;
    if (from.status === 'completed') return 'completed';
    return from.status;
  };

  const uniqueModels = Array.from(new Set([
    ...embeddings.map(e => e.model),
    ...indexes.map(i => i.model)
  ]));

  return (
    <div className={styles.pipeline}>
      {/* Main pipeline row */}
      <div className={styles.mainRow}>
        {mainStages.map((stage, i) => (
          <React.Fragment key={stage.key}>
            <StageNode
              stage={stage}
              stageSlug={stage.key}
              isControlActive={activeSet.has(stage.key)}
              isSelected={selectedStage === stage.key && !selectedModel}
              onClick={() => onSelectStage(stage.key, null)}
            />
            {i < mainStages.length - 1 && (
              <Connector status={getConnectorStatus(i)} />
            )}
          </React.Fragment>
        ))}

        {/* Branch to models (Embedding -> Index lanes) */}
        {uniqueModels.length > 0 && (
          <>
            <BranchConnector
              count={uniqueModels.length}
              statuses={uniqueModels.map(m => embeddings.find(e => e.model === m)?.status || 'pending')}
              fromStatus={mainStages[mainStages.length - 1]?.status}
            />
            <div className={styles.lanesWrapper}>
              <div 
                className={styles.lanesHeader}
                style={{ gridTemplateColumns: indexes.length > 0 ? 'minmax(120px, auto) 48px minmax(120px, auto)' : 'minmax(120px, auto)' }}
              >
                <div className={styles.laneHeaderCell}>Embedding</div>
                {indexes.length > 0 && (
                  <>
                    <div /> {/* Connector placeholder */}
                    <div className={styles.laneHeaderCell}>Index</div>
                  </>
                )}
              </div>
              <div 
                className={styles.lanesGrid}
                style={{ gridTemplateColumns: indexes.length > 0 ? 'minmax(120px, auto) 48px minmax(120px, auto)' : 'minmax(120px, auto)' }}
              >
                {uniqueModels.map(modelName => {
                  const emb = embeddings.find(e => e.model === modelName);
                  const idx = indexes.find(i => i.model === modelName);
                  
                  const connectorStatus = emb?.status === 'completed' && idx
                    ? (idx.status === 'pending' ? 'pending' : idx.status)
                    : (emb?.status || 'pending');

                  return (
                    <React.Fragment key={modelName}>
                      {emb ? (
                        <ModelNode
                          model={emb}
                          type="embed"
                          isControlActive={activeSet.has(`embed.${emb.model}`)}
                          isSelected={selectedStage === 'embedding' && selectedModel === emb.model}
                          onClick={() => onSelectStage('embedding', emb.model)}
                        />
                      ) : (
                        <div className={styles.modelNodePlaceholder} />
                      )}

                      {indexes.length > 0 && (
                        <>
                          <Connector status={connectorStatus} />
                          {idx ? (
                            <ModelNode
                              model={idx}
                              type="index"
                              isControlActive={activeSet.has(`index.${idx.model}`)}
                              isSelected={selectedStage === 'index' && selectedModel === idx.model}
                              onClick={() => onSelectStage('index', idx.model)}
                            />
                          ) : (
                            <div className={styles.modelNodePlaceholder} />
                          )}
                        </>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Legend */}
      <div className={styles.legend}>
        {Object.entries(STATUS_COLORS).map(([status, color]) => (
          <div key={status} className={styles.legendItem}>
            <span className={styles.legendDot} style={{ background: color }} />
            <span className={styles.legendLabel}>{status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

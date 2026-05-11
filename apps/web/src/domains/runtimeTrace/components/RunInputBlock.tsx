import { useState } from 'react';
import { Badge } from '@/shared/ui';
import type { RunInput } from '../aggregator';
import styles from './TraceV2.module.css';

interface Props {
  input: RunInput;
}

function fmt(ms?: number): string {
  if (ms == null) return '';
  if (ms >= 60_000) return `${Math.round(ms / 60_000)}m`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(0)}s`;
  return `${ms}ms`;
}

export function RunInputBlock({ input }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const { limits } = input;
  const hasLimits =
    limits.maxSteps != null ||
    limits.maxTools != null ||
    limits.maxRetries != null ||
    limits.toolTimeoutMs != null ||
    limits.wallTimeMs != null;

  return (
    <div className={`${styles.block} ${styles.blockInput}`}>
      <div className={styles.blockHeader} onClick={() => setCollapsed((v) => !v)} style={{ cursor: 'pointer', userSelect: 'none' }}>
        <span>↘ Input</span>
        {input.agent?.loggingLevel && (
          <Badge tone="neutral">logging: {input.agent.loggingLevel}</Badge>
        )}
        {input.model && <Badge tone="info">{input.model}</Badge>}
        <span style={{ marginLeft: 'auto', opacity: 0.4, fontSize: '0.7rem' }}>{collapsed ? '▶' : '▼'}</span>
      </div>
      {!collapsed && <div className={styles.blockBody}>
        <div className={styles.inputGrid}>

          {/* User request */}
          {input.userRequest && (
            <div className={`${styles.inputSection} ${styles.inputSectionFull}`}>
              <div className={styles.inputLabel}>Запрос</div>
              <div className={styles.inputRequest}>{input.userRequest}</div>
            </div>
          )}

          {/* Execution limits */}
          {hasLimits && (
            <div className={styles.inputSection}>
              <div className={styles.inputLabel}>Лимиты</div>
              <div className={styles.inputLimits}>
                {limits.maxSteps != null && (
                  <div className={styles.inputLimitItem}>
                    <span className={styles.inputLimitName}>Steps</span>
                    <span className={styles.inputLimitValue}>{limits.maxSteps}</span>
                  </div>
                )}
                {limits.maxTools != null && (
                  <div className={styles.inputLimitItem}>
                    <span className={styles.inputLimitName}>Tools</span>
                    <span className={styles.inputLimitValue}>{limits.maxTools}</span>
                  </div>
                )}
                {limits.maxRetries != null && (
                  <div className={styles.inputLimitItem}>
                    <span className={styles.inputLimitName}>Retries</span>
                    <span className={styles.inputLimitValue}>{limits.maxRetries}</span>
                  </div>
                )}
                {limits.toolTimeoutMs != null && (
                  <div className={styles.inputLimitItem}>
                    <span className={styles.inputLimitName}>Tool timeout</span>
                    <span className={styles.inputLimitValue}>{fmt(limits.toolTimeoutMs)}</span>
                  </div>
                )}
                {limits.wallTimeMs != null && (
                  <div className={styles.inputLimitItem}>
                    <span className={styles.inputLimitName}>Wall time</span>
                    <span className={styles.inputLimitValue}>{fmt(limits.wallTimeMs)}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tools */}
          {input.tools && input.tools.length > 0 && (
            <div className={styles.inputSection}>
              <div className={styles.inputLabel}>Инструменты</div>
              <div className={styles.inputTools}>
                {input.tools.map((t) => (
                  <Badge key={t.slug} tone="neutral">{t.slug}</Badge>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>}
    </div>
  );
}

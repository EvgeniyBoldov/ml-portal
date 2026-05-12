import { useState } from 'react';
import type { TraceArtifacts } from '../artifacts';
import styles from './TraceArtifactsView.module.css';

interface TraceArtifactsViewProps {
  artifacts: TraceArtifacts;
  className?: string;
  titleClassName?: string;
  preClassName?: string;
}

// --- Helper components ---

function CollapsibleSection({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={styles.section}>
      <button className={styles.sectionToggle} onClick={() => setOpen((v) => !v)}>
        {open ? '▼' : '▶'} {title}
      </button>
      {open && <div className={styles.sectionContent}>{children}</div>}
    </div>
  );
}

function KeyValueTable({ data, limit = 10 }: { data: Record<string, unknown>; limit?: number }) {
  const entries = Object.entries(data).slice(0, limit);
  const hasMore = Object.keys(data).length > limit;
  return (
    <table className={styles.kvTable}>
      <tbody>
        {entries.map(([key, val]) => (
          <tr key={key}>
            <td className={styles.kvKey}>{key}</td>
            <td className={styles.kvValue}>
              {typeof val === 'string' ? (
                val
              ) : val === null || val === undefined ? (
                '—'
              ) : typeof val === 'object' ? (
                <code className={styles.code}>{JSON.stringify(val).slice(0, 200)}</code>
              ) : (
                String(val)
              )}
            </td>
          </tr>
        ))}
        {hasMore && (
          <tr>
            <td className={styles.kvKey} colSpan={2}>... and more fields</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'success' | 'warn' | 'danger' | 'info' }) {
  return <span className={`${styles.badge} ${styles[`badge-${tone}`]}`}>{children}</span>;
}

// --- Artifact-specific cards ---

interface LLMMessage {
  role?: string;
  content?: string;
  name?: string;
  tool_calls?: Array<{ id?: string; type?: string; function?: { name?: string; arguments?: string } }>;
}

function formatMessagesForDisplay(data: Record<string, unknown>): LLMMessage[] | null {
  const messages = data.messages ?? data.messages_sent;
  if (Array.isArray(messages)) return messages as LLMMessage[];
  if (data.role && data.content) return [{ role: String(data.role), content: String(data.content) }];
  return null;
}

function LLMRequestCard({ data }: { data: unknown }) {
  if (!data || typeof data !== 'object') {
    return <div className={styles.emptyState}>No LLM request data</div>;
  }
  
  const d = data as Record<string, unknown>;
  const model = String(d.model ?? d.provider_model ?? d.model_id ?? '—');
  const messages = formatMessagesForDisplay(d);
  const temperature = d.temperature ?? (d.params && typeof d.params === 'object' ? (d.params as Record<string, unknown>).temperature : undefined);
  const maxTokens = d.max_tokens ?? d.maxTokens ?? (d.params && typeof d.params === 'object' ? (d.params as Record<string, unknown>).max_tokens : undefined);
  
  // Check if this is brief mode (only hashes/lengths, no real data)
  const isBriefMode = Boolean(
    !messages && (d.messages_hash || d.messages_length || d.system_prompt_hash),
  );
  
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.cardMeta}>
          <Badge tone="info">{model}</Badge>
          {temperature !== undefined && <span className={styles.metaItem}>temp: {Number(temperature).toFixed(1)}</span>}
          {maxTokens !== undefined && <span className={styles.metaItem}>max_tokens: {Number(maxTokens)}</span>}
        </div>
      </div>
      
      {isBriefMode && (
        <div className={styles.briefNotice}>
          <Badge tone="neutral">brief mode</Badge>
          <span className={styles.briefText}>Full messages not stored. Enable "full" logging level to see content.</span>
          {d.messages_length !== undefined && <span className={styles.briefStat}>({Number(d.messages_length)} chars)</span>}
        </div>
      )}
      
      {messages && messages.length > 0 && (
        <div className={styles.messagesList}>
          {messages.map((m, i) => (
            <div key={i} className={styles.messageItem}>
              <div className={`${styles.messageRole} ${styles[`role${m.role ?? 'user'}`]}`}>
                {m.role ?? 'user'}
              </div>
              <div className={styles.messageContent}>
                {m.content ? (
                  <pre className={styles.messageText}>{m.content}</pre>
                ) : m.tool_calls ? (
                  <div className={styles.toolCalls}>
                    {m.tool_calls.map((tc, j) => (
                      <div key={j} className={styles.toolCall}>
                        <code className={styles.toolName}>🔧 {tc.function?.name ?? tc.type ?? 'tool'}</code>
                        {tc.function?.arguments && (
                          <pre className={styles.toolArgs}>{tc.function.arguments}</pre>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className={styles.emptyContent}>—</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LLMResponseCard({ data }: { data: unknown }) {
  if (typeof data === 'string') {
    return (
      <div className={styles.card}>
        <pre className={styles.responseContent}>{data}</pre>
      </div>
    );
  }
  
  if (!data || typeof data !== 'object') {
    return <pre className={styles.code}>{JSON.stringify(data, null, 2)}</pre>;
  }
  
  const d = data as Record<string, unknown>;
  const content = d.content ?? d.text ?? d.response;
  
  // Check for brief mode
  const isBriefMode = !content && (d.content_hash || d.content_length || d.response_hash);
  
  if (isBriefMode) {
    return (
      <div className={styles.card}>
        <div className={styles.briefNotice}>
          <Badge tone="neutral">brief mode</Badge>
          <span className={styles.briefText}>Full response not stored. Enable "full" logging level to see content.</span>
          {d.content_length !== undefined && <span className={styles.briefStat}>({Number(d.content_length)} chars)</span>}
        </div>
      </div>
    );
  }
  
  return (
    <div className={styles.card}>
      {content !== undefined && (
        <pre className={styles.responseContent}>{typeof content === 'string' ? content : JSON.stringify(content, null, 2)}</pre>
      )}
      {d.choices !== undefined && Array.isArray(d.choices) && (
        <CollapsibleSection title={`Choices (${d.choices.length})`}>
          <pre className={styles.code}>{JSON.stringify(d.choices, null, 2)}</pre>
        </CollapsibleSection>
      )}
    </div>
  );
}

function ValidationCard({ data }: { data: unknown }) {
  if (!data || typeof data !== 'object') return <pre className={styles.code}>{JSON.stringify(data, null, 2)}</pre>;
  const d = data as Record<string, unknown>;
  const status = String(d.status ?? 'unknown');
  const tone = status === 'ok' || status === 'valid' ? 'success' : status === 'error' ? 'danger' : 'warn';
  return (
    <div className={styles.card}>
      <div className={styles.cardRow}>
        <span className={styles.cardLabel}>Status:</span>
        <Badge tone={tone}>{status}</Badge>
      </div>
      {d.error !== undefined && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Error:</span>
          <span className={styles.errorText}>{String(d.error)}</span>
        </div>
      )}
      {d.fallback_applied !== undefined && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Fallback:</span>
          <Badge tone={d.fallback_applied ? 'warn' : 'neutral'}>{d.fallback_applied ? 'applied' : 'none'}</Badge>
        </div>
      )}
    </div>
  );
}

function DecisionCard({ data }: { data: unknown }) {
  if (!data || typeof data !== 'object') return <pre className={styles.code}>{JSON.stringify(data, null, 2)}</pre>;
  const d = data as Record<string, unknown>;
  return (
    <div className={styles.card}>
      <div className={styles.cardRow}>
        <span className={styles.cardLabel}>Kind:</span>
        <Badge tone="info">{String(d.kind ?? d.action_type ?? d.decision ?? '—')}</Badge>
      </div>
      {d.rationale !== undefined && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Rationale:</span>
          <span className={styles.textSecondary}>{String(d.rationale)}</span>
        </div>
      )}
      {d.agent_slug !== undefined && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Agent:</span>
          <code className={styles.codeInline}>{String(d.agent_slug)}</code>
        </div>
      )}
      {d.risk !== undefined && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Risk:</span>
          <Badge tone={d.risk === 'high' ? 'danger' : d.risk === 'medium' ? 'warn' : 'success'}>{String(d.risk)}</Badge>
        </div>
      )}
      {d.requires_confirmation !== undefined && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Needs confirm:</span>
          <Badge tone={d.requires_confirmation ? 'warn' : 'neutral'}>{d.requires_confirmation ? 'yes' : 'no'}</Badge>
        </div>
      )}
    </div>
  );
}

function BudgetCard({ data }: { data: unknown }) {
  if (!data || typeof data !== 'object') return <pre className={styles.code}>{JSON.stringify(data, null, 2)}</pre>;
  const d = data as Record<string, unknown>;
  
  const kind = String(d.kind ?? d.reason ?? d.code ?? 'budget');
  const isInit = kind === 'budget_policy' || kind === 'budget_init' || (d.max_steps !== undefined && d.used === undefined && d.consumed === undefined);
  const isExceeded = kind === 'budget_limit_exceeded' || kind === 'no_successful_operation_result';
  
  // For init events, show limits
  if (isInit) {
    return (
      <div className={styles.card}>
        <div className={styles.budgetHeader}>
          <Badge tone="info">Execution Limits</Badge>
        </div>
        <div className={styles.budgetLimits}>
          {d.max_steps !== undefined && (
            <div className={styles.budgetLimitItem}>
              <span className={styles.budgetLimitName}>Max Steps</span>
              <span className={styles.budgetLimitValue}>{Number(d.max_steps)}</span>
            </div>
          )}
          {d.max_tool_calls_total !== undefined && (
            <div className={styles.budgetLimitItem}>
              <span className={styles.budgetLimitName}>Max Tool Calls</span>
              <span className={styles.budgetLimitValue}>{Number(d.max_tool_calls_total)}</span>
            </div>
          )}
          {d.max_retries !== undefined && (
            <div className={styles.budgetLimitItem}>
              <span className={styles.budgetLimitName}>Max Retries</span>
              <span className={styles.budgetLimitValue}>{Number(d.max_retries)}</span>
            </div>
          )}
          {d.tool_timeout_ms !== undefined && (
            <div className={styles.budgetLimitItem}>
              <span className={styles.budgetLimitName}>Tool Timeout</span>
              <span className={styles.budgetLimitValue}>{Number(d.tool_timeout_ms)}ms</span>
            </div>
          )}
          {d.max_wall_time_ms !== undefined && (
            <div className={styles.budgetLimitItem}>
              <span className={styles.budgetLimitName}>Wall Time</span>
              <span className={styles.budgetLimitValue}>{Number(d.max_wall_time_ms)}ms</span>
            </div>
          )}
        </div>
      </div>
    );
  }
  
  // For consumed events, show progress
  const used = Number(d.used ?? d.consumed ?? d.steps_used ?? 0);
  const limit = Number(d.limit ?? d.max_steps ?? 0);
  const remaining = d.remaining !== undefined ? Number(d.remaining) : limit > 0 ? limit - used : undefined;
  const percentage = limit > 0 ? Math.round((used / limit) * 100) : 0;
  
  return (
    <div className={styles.card}>
      <div className={styles.budgetHeader}>
        <Badge tone={isExceeded ? 'danger' : 'info'}>{isExceeded ? '⚠ Limit Reached' : 'Budget Usage'}</Badge>
      </div>
      <div className={styles.budgetBar}>
        <div 
          className={styles.budgetBarFill} 
          style={{ 
            width: `${Math.min(percentage, 100)}%`, 
            background: isExceeded ? 'var(--danger)' : percentage > 90 ? 'var(--danger)' : percentage > 70 ? 'var(--warn)' : 'var(--success)' 
          }} 
        />
      </div>
      <div className={styles.budgetStats}>
        <div className={styles.budgetStat}>
          <span className={styles.budgetLabel}>Consumed</span>
          <span className={styles.budgetValue}>{used}</span>
        </div>
        <div className={styles.budgetStat}>
          <span className={styles.budgetLabel}>Limit</span>
          <span className={styles.budgetValue}>{limit}</span>
        </div>
        {remaining !== undefined && (
          <div className={styles.budgetStat}>
            <span className={styles.budgetLabel}>Remaining</span>
            <span className={`${styles.budgetValue} ${remaining === 0 ? styles.budgetExhausted : ''}`}>
              {remaining}
            </span>
          </div>
        )}
      </div>
      {kind !== 'budget' && kind !== 'budget_consumed' && (
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Type:</span>
          <Badge tone={isExceeded ? 'danger' : 'neutral'}>{kind}</Badge>
        </div>
      )}
    </div>
  );
}

function OperationCard({ input, output }: { input: unknown; output: unknown }) {
  // Extract operation name from various possible fields
  const inputData = input && typeof input === 'object' ? input as Record<string, unknown> : {};
  const operationName = String(
    inputData.operation ?? 
    inputData.slug ?? 
    inputData.tool ?? 
    inputData.name ?? 
    inputData.operation_slug ??
    '—'
  );
  
  // Try to parse arguments - they might be stringified JSON
  let argumentsData: Record<string, unknown> | undefined;
  const rawArgs = inputData.arguments ?? inputData.parameters ?? inputData.input ?? inputData.args;
  
  if (typeof rawArgs === 'string') {
    try {
      argumentsData = JSON.parse(rawArgs);
    } catch {
      argumentsData = { raw: rawArgs };
    }
  } else if (typeof rawArgs === 'object' && rawArgs !== null) {
    argumentsData = rawArgs as Record<string, unknown>;
  }
  
  // Extract output/result
  const outputData = output && typeof output === 'object' ? output as Record<string, unknown> : {};
  const result = outputData.result ?? outputData.output ?? outputData.data ?? output;
  const success = outputData.success ?? outputData.status;
  
  return (
    <div className={styles.card}>
      <div className={styles.operationHeader}>
        <code className={styles.operationName}>{operationName}</code>
        {success !== undefined && (
          <Badge tone={success === true || success === 'success' ? 'success' : 'danger'}>
            {success === true || success === 'success' ? '✓ success' : '✗ failed'}
          </Badge>
        )}
      </div>
      
      {argumentsData !== undefined && Object.keys(argumentsData).length > 0 && (
        <CollapsibleSection title="Arguments" defaultOpen={true}>
          <KeyValueTable data={argumentsData} />
        </CollapsibleSection>
      )}
      
      {result !== undefined && (
        <CollapsibleSection title="Result">
          {typeof result === 'object' ? (
            <KeyValueTable data={result as Record<string, unknown>} />
          ) : (
            <pre className={styles.code}>{String(result)}</pre>
          )}
        </CollapsibleSection>
      )}
    </div>
  );
}

function ErrorContractCard({ data }: { data: unknown }) {
  if (!data || typeof data !== 'object') return <pre className={styles.code}>{JSON.stringify(data, null, 2)}</pre>;
  const d = data as Record<string, unknown>;
  return (
    <div className={`${styles.card} ${styles.cardError}`}>
      <div className={styles.cardRow}>
        <span className={styles.cardLabel}>Code:</span>
        <Badge tone="danger">{String(d.code ?? 'error')}</Badge>
      </div>
      {d.user_message !== undefined && (
        <div className={styles.cardSection}>
          <div className={styles.cardLabel}>User message:</div>
          <div className={styles.cardText}>{String(d.user_message)}</div>
        </div>
      )}
      {d.operator_message !== undefined && (
        <div className={styles.cardSection}>
          <div className={styles.cardLabel}>Operator message:</div>
          <div className={styles.cardText}>{String(d.operator_message)}</div>
        </div>
      )}
      <div className={styles.cardRow}>
        {d.retryable !== undefined && (
          <span>Retryable: <Badge tone={d.retryable ? 'warn' : 'neutral'}>{d.retryable ? 'yes' : 'no'}</Badge></span>
        )}
        {d.recoverable !== undefined && (
          <span>Recoverable: <Badge tone={d.recoverable ? 'success' : 'neutral'}>{d.recoverable ? 'yes' : 'no'}</Badge></span>
        )}
      </div>
    </div>
  );
}

// --- Main component ---

export function TraceArtifactsView({
  artifacts,
  className,
}: TraceArtifactsViewProps) {
  const hasAny = Object.values(artifacts).some((v) => v !== undefined && v !== null);
  if (!hasAny) {
    return <div className={`${styles.empty} ${className}`}>No extracted artifacts</div>;
  }

  return (
    <div className={`${styles.container} ${className}`}>
      {artifacts.prompt !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Prompt</div>
          <CollapsibleSection title="View prompt">
            <pre className={styles.code}>{typeof artifacts.prompt === 'string' ? artifacts.prompt : JSON.stringify(artifacts.prompt, null, 2)}</pre>
          </CollapsibleSection>
        </section>
      )}

      {artifacts.llmRequest !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>LLM Request</div>
          <LLMRequestCard data={artifacts.llmRequest} />
        </section>
      )}

      {artifacts.llmRawResponse !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>LLM Response</div>
          <LLMResponseCard data={artifacts.llmRawResponse} />
        </section>
      )}

      {artifacts.llmParsedResponse !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Parsed Response</div>
          <pre className={styles.code}>{JSON.stringify(artifacts.llmParsedResponse, null, 2)}</pre>
        </section>
      )}

      {artifacts.validation !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Validation</div>
          <ValidationCard data={artifacts.validation} />
        </section>
      )}

      {artifacts.decision !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Decision</div>
          <DecisionCard data={artifacts.decision} />
        </section>
      )}

      {artifacts.budget !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Budget</div>
          <BudgetCard data={artifacts.budget} />
        </section>
      )}

      {(artifacts.operationInput !== undefined || artifacts.operationOutput !== undefined) && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Tool Call</div>
          <OperationCard input={artifacts.operationInput} output={artifacts.operationOutput} />
        </section>
      )}

      {artifacts.errorContract !== undefined && (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>Error</div>
          <ErrorContractCard data={artifacts.errorContract} />
        </section>
      )}
    </div>
  );
}

export default TraceArtifactsView;

import { useState } from 'react';
import { Badge } from '@/shared/ui';
import type {
  TraceEntry,
  LLMTraceEntry,
  ToolTraceEntry,
  DecisionTraceEntry,
  ErrorTraceEntry,
} from '../aggregator';
import { BudgetBadge } from './BudgetBadge';
import styles from './TraceV2.module.css';

// ─── Helpers ───────────────────────────────────────────────────────────────

function formatDate(s?: string): string {
  if (!s) return '';
  return new Date(s).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function formatMs(ms?: number): string {
  if (ms == null) return '';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

function tryParseJson(v: unknown): unknown {
  if (typeof v === 'string') {
    try { return JSON.parse(v); } catch { return v; }
  }
  return v;
}

function djb2(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h) ^ s.charCodeAt(i);
  return (h >>> 0).toString(16).padStart(8, '0');
}

function countWords(s: string): number {
  return s.trim().split(/\s+/).filter(Boolean).length;
}

function prettyJson(v: unknown): string {
  if (v == null) return '';
  const parsed = tryParseJson(v);
  if (typeof parsed === 'string') return parsed;
  return JSON.stringify(parsed, null, 2);
}

// ─── IOField — single labelled field ───────────────────────────────────────

interface IOFieldDef {
  label: string;
  value: unknown;
  /** if true, render as monospace code block */
  code?: boolean;
}

function IOFieldItem({ field }: { field: IOFieldDef }) {
  const text = prettyJson(field.value);
  if (!text) return null;
  return (
    <div className={styles.ioField}>
      <div className={styles.ioFieldLabel}>{field.label}</div>
      {field.code ? (
        <pre className={styles.ioFieldValueCode}>{text}</pre>
      ) : (
        <div className={styles.ioFieldValue}>{text}</div>
      )}
    </div>
  );
}

// ─── IOViewer — universal request/response switcher ────────────────────────

type IOSide = 'in' | 'out';

interface IOPanel {
  /** Tab label, e.g. "↑ Request" */
  label: string;
  side: IOSide;
  /** Fields to render in the panel */
  fields?: IOFieldDef[];
  /** LLM messages array (alternative to fields) */
  messages?: Array<Record<string, unknown>>;
  /** Plain text block (alternative to fields/messages) */
  text?: string;
  /** Brief-mode: show notice instead of content */
  brief?: boolean;
  briefHint?: string;
  briefHashes?: Array<{ key: string; value: string }>;
  /** Optional stat chips in panel header */
  stats?: Array<{ label: string }>;
  /** Optional hash to show in panel header */
  hash?: string | null;
}

function IOViewer({ panels, defaultSide = 'in' }: { panels: [IOPanel, IOPanel]; defaultSide?: IOSide }) {
  const [active, setActive] = useState<IOSide>(defaultSide);
  const panel = panels.find((p) => p.side === active) ?? panels[0];

  return (
    <div className={styles.ioViewer}>
      {/* Tabs */}
      <div className={styles.ioTabs}>
        {panels.map((p) => {
          const isActive = p.side === active;
          const activeCls = isActive
            ? `${styles.ioTabActive} ${p.side === 'in' ? styles.ioTabActiveIn : styles.ioTabActiveOut}`
            : '';
          return (
            <button key={p.side} className={`${styles.ioTab} ${activeCls}`} onClick={() => setActive(p.side)}>
              {p.label}
              {p.brief && <span style={{ opacity: 0.55, fontSize: '0.6rem', marginLeft: 4 }}>brief</span>}
            </button>
          );
        })}
      </div>

      {/* Panel */}
      <div className={styles.ioPanel}>
        {/* Header */}
        <div className={styles.ioPanelHeader}>
          <div className={styles.ioPanelMeta}>
            {panel.stats?.map((s, i) => (
              <span key={i} className={styles.ioPanelStatChip}>{s.label}</span>
            ))}
            {panel.hash && (
              <span className={styles.ioPanelHashChip}>{panel.hash}</span>
            )}
          </div>
        </div>

        {/* Content */}
        <div className={styles.ioPanelContent}>
          {panel.brief ? (
            <div className={styles.ioBriefNotice}>
              <span className={styles.ioBriefIcon}>⚠</span>
              <div className={styles.ioBriefText}>
                <div>{panel.briefHint ?? 'Brief logging mode — данные не записаны.'}</div>
                <div>Переключите агента на <strong>full</strong> logging.</div>
                {panel.briefHashes?.map((h) => (
                  <div key={h.key} className={styles.ioBriefHash}>{h.key}: {h.value}</div>
                ))}
              </div>
            </div>
          ) : panel.messages ? (
            <div className={styles.ioMessages}>
              {panel.messages.map((msg, i) => {
                const role = String(msg.role ?? 'unknown');
                const content = typeof msg.content === 'string'
                  ? msg.content
                  : JSON.stringify(msg.content, null, 2);
                const bgCls =
                  role === 'system' ? styles.ioMessageSystem
                  : role === 'user' ? styles.ioMessageUser
                  : role === 'assistant' ? styles.ioMessageAssistant
                  : styles.ioMessageTool;
                const roleCls =
                  role === 'system' ? styles.ioMessageRoleSystem
                  : role === 'user' ? styles.ioMessageRoleUser
                  : role === 'assistant' ? styles.ioMessageRoleAssistant
                  : styles.ioMessageRoleTool;
                return (
                  <div key={i} className={`${styles.ioMessage} ${bgCls}`}>
                    <div className={`${styles.ioMessageRole} ${roleCls}`}>{role}</div>
                    <div className={styles.ioMessageContent}>{content}</div>
                  </div>
                );
              })}
            </div>
          ) : panel.text != null ? (
            <div className={styles.ioFields}>
              <pre className={styles.ioFieldValueCode}>{panel.text}</pre>
            </div>
          ) : panel.fields && panel.fields.length > 0 ? (
            <div className={styles.ioFields}>
              {panel.fields.map((f, i) => <IOFieldItem key={i} field={f} />)}
            </div>
          ) : (
            <div className={`${styles.ioBriefNotice} ${styles.ioBriefNoticeNeutral}`}>
              <span className={styles.ioBriefIcon}>—</span>
              <div className={styles.ioBriefText}>Нет данных</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── LLM Entry Body ────────────────────────────────────────────────────────

function LLMEntryBody({ entry }: { entry: LLMTraceEntry }) {
  const reqRaw = entry.rawEvents[0]?.raw.raw ?? {};
  const respRaw = entry.rawEvents.find((e) => e.raw_type === 'llm_response')?.raw.raw ?? {};

  const hasMessages = !!(entry.messages && (entry.messages as unknown[]).length > 0);
  const isReqBrief = entry.isBriefMode && !hasMessages;
  const isRespBrief = entry.isBriefMode && !entry.responseContent;

  const reqText = hasMessages
    ? (entry.messages as Array<Record<string, unknown>>)
        .map((m) => `[${String(m.role ?? '').toUpperCase()}]\n${typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2)}`)
        .join('\n\n')
    : '';
  const reqHash = reqText ? `djb2:${djb2(reqText)}` : null;
  const respHash = entry.responseContent ? `djb2:${djb2(entry.responseContent)}` : null;

  const metaFields = [
    entry.model ? `model: ${entry.model}` : null,
    entry.temperature != null ? `temp: ${entry.temperature}` : null,
    entry.maxTokens != null ? `max_tokens: ${entry.maxTokens}` : null,
  ].filter(Boolean) as string[];

  const panels: [IOPanel, IOPanel] = [
    {
      label: '↑ Request',
      side: 'in',
      messages: hasMessages ? (entry.messages as Array<Record<string, unknown>>) : undefined,
      brief: isReqBrief,
      briefHint: 'Brief logging mode — messages не записаны.',
      briefHashes: [
        ...(reqRaw.messages_hash ? [{ key: 'messages', value: String(reqRaw.messages_hash) }] : []),
        ...(reqRaw.system_prompt_hash ? [{ key: 'system_prompt', value: String(reqRaw.system_prompt_hash) }] : []),
      ],
      stats: [
        ...(hasMessages ? [{ label: `${(entry.messages as unknown[]).length} messages` }] : []),
        ...(reqText ? [{ label: `${countWords(reqText)} words` }] : []),
        ...metaFields.map((f) => ({ label: f })),
      ],
      hash: reqHash,
    },
    {
      label: '↓ Response',
      side: 'out',
      text: entry.responseContent ?? undefined,
      brief: isRespBrief,
      briefHint: 'Brief logging mode — ответ не записан.',
      briefHashes: respRaw.content_hash ? [{ key: 'content', value: String(respRaw.content_hash) }] : [],
      stats: [
        ...(entry.responseContent ? [{ label: `${countWords(entry.responseContent)} words` }] : []),
        ...(entry.tokensOut != null ? [{ label: `${entry.tokensOut} tokens` }] : []),
      ],
      hash: respHash,
    },
  ];

  return (
    <div>
      <IOViewer panels={panels} />
      <details className={styles.rawDetails} onClick={(e: MouseEvent) => e.stopPropagation()}>
        <summary onClick={(e: MouseEvent) => e.stopPropagation()}>Show raw ({entry.rawEvents.length} events)</summary>
        <pre className={styles.entryPre}>
          {entry.rawEvents.map((e) => JSON.stringify(e.raw.raw, null, 2)).join('\n\n---\n\n')}
        </pre>
      </details>
    </div>
  );
}

// ─── Tool Entry Body ───────────────────────────────────────────────────────

function ToolEntryBody({ entry }: { entry: ToolTraceEntry }) {
  const isBriefOutput =
    entry.output != null &&
    typeof entry.output === 'object' &&
    (entry.output as Record<string, unknown>)._brief === true;

  const inputJson = entry.input != null ? prettyJson(entry.input) : null;
  const outputJson = !isBriefOutput && entry.output != null ? prettyJson(entry.output) : null;
  const inputHash = inputJson ? `djb2:${djb2(inputJson)}` : null;
  const outputHash = outputJson ? `djb2:${djb2(outputJson)}` : null;

  const briefOutputMeta = isBriefOutput
    ? (entry.output as Record<string, unknown>)
    : null;

  const panels: [IOPanel, IOPanel] = [
    {
      label: '↑ Arguments',
      side: 'in',
      fields: inputJson ? [{ label: 'arguments', value: entry.input, code: true }] : undefined,
      hash: inputHash,
      stats: inputJson ? [{ label: `${countWords(inputJson)} words` }] : [],
    },
    {
      label: entry.status === 'failed' ? '↓ Error' : '↓ Result',
      side: 'out',
      brief: isBriefOutput,
      briefHint: 'Brief logging mode — результат не записан.',
      briefHashes: briefOutputMeta?.hash
        ? [{ key: 'result', value: String(briefOutputMeta.hash) + (briefOutputMeta.length != null ? ` (${briefOutputMeta.length} chars)` : '') }]
        : [],
      fields: outputJson
        ? [{ label: 'result', value: entry.output, code: true }]
        : !isBriefOutput && entry.status === 'failed'
          ? [{ label: 'status', value: 'Tool call failed — no result recorded', code: false }]
          : undefined,
      hash: outputHash,
    },
  ];

  return (
    <div>
      {entry.retries.length > 0 && (
        <div className={styles.entrySection}>
          <div className={styles.entrySectionTitle}>Retries ({entry.retries.length})</div>
          <div className={styles.retries}>
            {entry.retries.map((r, i) => (
              <div key={i} className={styles.retry}>
                <strong>↻ {i + 1}:</strong> {r.reason}
                {r.error && <span> — {r.error}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
      <IOViewer panels={panels} defaultSide={entry.output != null ? 'out' : 'in'} />
      <details className={styles.rawDetails} onClick={(e: MouseEvent) => e.stopPropagation()}>
        <summary onClick={(e: MouseEvent) => e.stopPropagation()}>Show raw ({entry.rawEvents.length} events)</summary>
        <pre className={styles.entryPre}>
          {entry.rawEvents.map((e) => JSON.stringify(e.raw.raw, null, 2)).join('\n\n---\n\n')}
        </pre>
      </details>
    </div>
  );
}

// ─── Decision Entry Body ───────────────────────────────────────────────────

function DecisionEntryBody({ entry }: { entry: DecisionTraceEntry }) {
  return (
    <div className={styles.entrySection}>
      <pre className={styles.entryPre}>{JSON.stringify(entry.details, null, 2)}</pre>
    </div>
  );
}

// ─── Error Entry Body ──────────────────────────────────────────────────────

function ErrorEntryBody({ entry }: { entry: ErrorTraceEntry }) {
  return (
    <div>
      <div className={`${styles.finalError} ${styles.entrySection}`}>
        <div className={styles.finalErrorCode}>{entry.code}</div>
        {entry.userMessage && <div className={styles.finalErrorMsg}>{entry.userMessage}</div>}
        {entry.operatorMessage && entry.operatorMessage !== entry.userMessage && (
          <div className={styles.finalErrorMsg} style={{ opacity: 0.7 }}>{entry.operatorMessage}</div>
        )}
      </div>
      {entry.debug != null && (
        <div className={styles.entrySection}>
          <div className={styles.entrySectionTitle}>Debug</div>
          <pre className={styles.entryPre}>{JSON.stringify(entry.debug, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Entry summary (collapsed) ────────────────────────────────────────────

function entrySummary(entry: TraceEntry): string {
  if (entry.type === 'llm') return entry.intent;
  if (entry.type === 'tool') {
    const retryStr = entry.retries.length > 0 ? ` ↻${entry.retries.length}` : '';
    return `${entry.toolName}${retryStr}`;
  }
  if (entry.type === 'decision') return entry.summary;
  if (entry.type === 'error') return entry.code;
  return '';
}

function entryLabel(entry: TraceEntry): { text: string; tone: 'info' | 'success' | 'warn' | 'danger' | 'neutral' } {
  if (entry.type === 'llm') return { text: 'LLM', tone: 'info' };
  if (entry.type === 'tool') {
    return {
      text: entry.status === 'failed' ? 'TOOL ✗' : 'TOOL ✓',
      tone: entry.status === 'failed' ? 'danger' : 'success',
    };
  }
  if (entry.type === 'decision') return { text: 'DECISION', tone: 'neutral' };
  if (entry.type === 'error') return { text: 'ERROR', tone: 'danger' };
  return { text: 'EVENT', tone: 'neutral' };
}

function entryBorderCls(entry: TraceEntry, cssModuleStyles: Record<string, string>): string {
  if (entry.type === 'llm') return cssModuleStyles.entryCardLlm;
  if (entry.type === 'tool') {
    return entry.status === 'failed' ? cssModuleStyles.entryCardToolFailed : cssModuleStyles.entryCardTool;
  }
  if (entry.type === 'decision') return cssModuleStyles.entryCardDecision;
  if (entry.type === 'error') return cssModuleStyles.entryCardError;
  return '';
}

// ─── TraceEntryCard ────────────────────────────────────────────────────────

interface TraceEntryCardProps {
  entry: TraceEntry;
  index: number;
}

export function TraceEntryCard({ entry, index }: TraceEntryCardProps) {
  const [expanded, setExpanded] = useState(false);
  const label = entryLabel(entry);
  const summary = entrySummary(entry);
  const borderCls = entryBorderCls(entry, styles);

  return (
    <div className={`${styles.entryCard} ${borderCls}`}>
      <div
        className={styles.entryHeader}
        onClick={() => setExpanded((v) => !v)}
      >
        <div className={styles.entryHeaderLeft}>
          <span className={styles.entryIndex}>#{index + 1}</span>
          <Badge tone={label.tone}>{label.text}</Badge>
          <span className={styles.entrySummary}>{summary}</span>
        </div>
        <div className={styles.entryHeaderRight}>
          <BudgetBadge budget={entry.budgetSnapshot} />
          {entry.startedAt && (
            <span className={styles.entryDatetime}>{formatDate(entry.startedAt)}</span>
          )}
          {entry.durationMs != null && (
            <span className={styles.entryDuration}>{formatMs(entry.durationMs)}</span>
          )}
          <span className={styles.entryToggle}>{expanded ? '▼' : '▶'}</span>
        </div>
      </div>

      {expanded && (
        <div className={styles.entryBody} onClick={(e) => e.stopPropagation()}>
          {entry.type === 'llm' && <LLMEntryBody entry={entry} />}
          {entry.type === 'tool' && <ToolEntryBody entry={entry} />}
          {entry.type === 'decision' && <DecisionEntryBody entry={entry} />}
          {entry.type === 'error' && <ErrorEntryBody entry={entry} />}
        </div>
      )}
    </div>
  );
}

// ─── RunTraceLog ───────────────────────────────────────────────────────────

interface RunTraceLogProps {
  entries: TraceEntry[];
}

export function RunTraceLog({ entries }: RunTraceLogProps) {
  if (entries.length === 0) {
    return (
      <div className={styles.traceLogEmpty}>
        Нет шагов в трейсе
      </div>
    );
  }

  return (
    <div className={styles.traceLog}>
      {entries.map((entry, i) => (
        <TraceEntryCard key={entry.id} entry={entry} index={i} />
      ))}
    </div>
  );
}

/**
 * RunInspector — right-panel detail view for a selected step.
 * Canonical observability contract: tabs (summary/input/output/context/raw)
 * with typed field rendering and parameter-level accordions.
 */
import { useMemo, useState, type ReactNode } from 'react';
import type { RunStep } from '../hooks/useSandboxRun';
import styles from './RunInspector.module.css';

type Tone = 'neutral' | 'info' | 'warn' | 'success' | 'danger';
type InspectTabKey = 'summary' | 'input' | 'output' | 'context' | 'raw';
type InspectFieldType =
  | 'datetime'
  | 'duration'
  | 'label'
  | 'labels'
  | 'json'
  | 'string'
  | 'bigstring'
  | 'number'
  | 'boolean';

interface InspectField {
  key: string;
  label: string;
  value: unknown;
  type: InspectFieldType;
  tone?: Tone;
}

interface InspectTabSpec {
  key: InspectTabKey;
  label: string;
  fields: InspectField[];
}

interface StepRefValue {
  kind?: string;
  id?: string;
  label?: string;
}

const STEP_META: Record<string, { label: string; icon: string; tone: Tone }> = {
  status: { label: 'Status', icon: '◉', tone: 'neutral' },
  thinking: { label: 'Thinking', icon: '💭', tone: 'neutral' },
  routing: { label: 'Routing', icon: '🔀', tone: 'info' },
  tool_call: { label: 'Tool call', icon: '🔧', tone: 'info' },
  tool_result: { label: 'Tool result', icon: '📋', tone: 'success' },
  planner_action: { label: 'Planner', icon: '📐', tone: 'info' },
  policy_decision: { label: 'Policy', icon: '🛡', tone: 'warn' },
  confirmation_required: { label: 'Confirmation', icon: '⚠', tone: 'warn' },
  waiting_input: { label: 'Waiting input', icon: '⏳', tone: 'warn' },
  stop: { label: 'Stop', icon: '⏹', tone: 'neutral' },
  final: { label: 'Final', icon: '✅', tone: 'success' },
  error: { label: 'Error', icon: '❌', tone: 'danger' },
};

const INPUT_KEYS = [
  'input',
  'args',
  'arguments',
  'parameters',
  'payload',
  'request',
  'request_payload',
  'messages',
  'prompt',
  'system_prompt',
  'llm_request',
  'available_agents',
  'candidate_agents',
  'available_tools',
  'context',
] as const;

const OUTPUT_KEYS = [
  'output',
  'result',
  'response',
  'data',
  'llm_response',
  'parsed_response',
  'final_answer',
  'answer',
  'selected_agent',
  'selected_tool',
  'tool_result',
  'observation',
] as const;

const CONTEXT_KEYS = [
  'id',
  'run_id',
  'branch_id',
  'snapshot_id',
  'tenant_id',
  'chat_id',
  'user_id',
  'agent_id',
  'agent_slug',
  'agent_name',
  'tool_id',
  'tool',
  'tool_slug',
  'tool_name',
  'operation',
  'operation_slug',
  'collection_id',
  'collection_slug',
  'collection_name',
  'model',
  'mode',
  'stage',
  'decision',
  'status',
  'branch_name',
  'snapshot_hash',
  'snapshot_label',
  'refs',
] as const;

const ERROR_KEYS = ['error', 'message', 'traceback', 'stack', 'code', 'details'] as const;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function fmtDateTime(value: number | string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ru-RU', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function titleFromKey(key: string): string {
  return key
    .split('_')
    .filter(Boolean)
    .map((chunk) => chunk[0].toUpperCase() + chunk.slice(1))
    .join(' ');
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID_PATTERN.test(value);
}

function getStepTitle(step: RunStep): string {
  if (step.type === 'tool_call' || step.type === 'tool_result') {
    const tool = step.data.tool;
    if (typeof tool === 'string' && tool.length > 0) return tool;
  }
  if (step.type === 'status') {
    const stage = step.data.stage;
    if (typeof stage === 'string' && stage.length > 0) return stage;
  }
  if (step.type === 'routing') {
    const slug = step.data.agent_slug;
    if (typeof slug === 'string' && slug.length > 0) return `→ ${slug}`;
  }
  if (step.type === 'planner_action') {
    const action = step.data.action_type ?? step.data.action;
    if (typeof action === 'string' && action.length > 0) return action;
  }
  return STEP_META[step.type]?.label ?? step.type;
}

function pickRecordByKeys(source: Record<string, unknown>, keys: readonly string[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    if (source[key] !== undefined) result[key] = source[key];
  }
  return result;
}

function sanitizeSectionRecord(value: unknown, fallbackKey: string): Record<string, unknown> {
  if (value === null || value === undefined) return {};
  if (typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  return { [fallbackKey]: value };
}

function omitKeys(source: Record<string, unknown>, keys: readonly string[]): Record<string, unknown> {
  const dropped = new Set(keys);
  return Object.fromEntries(Object.entries(source).filter(([key]) => !dropped.has(key)));
}

function resolveHumanReadableRef(record: Record<string, unknown>, key: string, value: string): string | null {
  if (!isUuid(value)) return null;

  const prefix = key.endsWith('_id') ? key.slice(0, -3) : null;
  const candidates = prefix
    ? [`${prefix}_slug`, `${prefix}_name`, `${prefix}_title`, `${prefix}_label`]
    : [];

  for (const candidateKey of candidates) {
    const candidate = record[candidateKey];
    if (typeof candidate === 'string' && candidate.trim().length > 0 && !isUuid(candidate)) {
      return `${candidate} (${value.slice(0, 8)})`;
    }
  }

  if (key === 'snapshot_id') return `Snapshot ${value.slice(0, 8)}`;
  if (key === 'branch_id') return `Branch ${value.slice(0, 8)}`;
  if (key === 'run_id') return `Run ${value.slice(0, 8)}`;
  if (key.endsWith('_id') || key === 'id') return `${value.slice(0, 8)}…`;
  return null;
}

function readRefsMap(raw: unknown): Record<string, StepRefValue> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  return raw as Record<string, StepRefValue>;
}

function resolveRefLabelById(refs: Record<string, StepRefValue>, id: string): string | null {
  for (const ref of Object.values(refs)) {
    if (typeof ref?.id === 'string' && ref.id === id && typeof ref.label === 'string' && ref.label.trim().length > 0) {
      return ref.label.trim();
    }
  }
  return null;
}

function resolveRefFromMap(refs: Record<string, StepRefValue>, key: string, value: unknown): string | null {
  if (!isUuid(value)) return null;
  const direct = refs[key];
  if (direct && typeof direct.label === 'string' && direct.label.trim().length > 0) {
    return direct.label;
  }
  return resolveRefLabelById(refs, value);
}

function normalizeValueWithRefs(value: unknown, refs: Record<string, StepRefValue>, currentKey?: string): unknown {
  if (typeof value === 'string' && isUuid(value)) {
    if (currentKey) {
      const direct = resolveRefFromMap(refs, currentKey, value);
      if (direct) return direct;
    }
    return resolveRefLabelById(refs, value) ?? value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeValueWithRefs(item, refs, currentKey));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, normalizeValueWithRefs(v, refs, k)]),
    );
  }
  return value;
}

function inferFieldType(key: string, value: unknown): InspectFieldType {
  const lowered = key.toLowerCase();
  if (lowered.includes('time') || lowered.endsWith('_at') || lowered === 'start' || lowered === 'end') return 'datetime';
  if (lowered.includes('duration') || lowered.endsWith('_ms') || lowered.endsWith('_seconds')) return 'duration';
  if (lowered.includes('status') || lowered.includes('decision') || lowered.includes('level') || lowered === 'mode') return 'label';
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item === 'string' || typeof item === 'number')) return 'labels';
    return 'json';
  }
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (value !== null && typeof value === 'object') return 'json';
  if (typeof value === 'string') {
    if (value.length > 240 || value.includes('\n')) return 'bigstring';
    return 'string';
  }
  return 'string';
}

function toneFromStatus(value: unknown): Tone | undefined {
  if (typeof value !== 'string') return undefined;
  const lowered = value.toLowerCase();
  if (lowered.includes('fail') || lowered.includes('error') || lowered.includes('deny') || lowered.includes('blocked')) return 'danger';
  if (lowered.includes('success') || lowered.includes('ok') || lowered.includes('complete')) return 'success';
  if (lowered.includes('wait') || lowered.includes('pending')) return 'warn';
  return undefined;
}

function mapToFields(record: Record<string, unknown>, refs: Record<string, StepRefValue> = {}): InspectField[] {
  return Object.entries(record).map(([key, rawValue]) => {
    const normalizedValue = normalizeValueWithRefs(rawValue, refs, key);
    const finalValue =
      typeof normalizedValue === 'string'
        ? resolveHumanReadableRef(record, key, normalizedValue) ?? normalizedValue
        : normalizedValue;
    const type = inferFieldType(key, rawValue);
    return {
      key,
      label: titleFromKey(key),
      value: finalValue,
      type,
      tone: type === 'label' ? toneFromStatus(finalValue) : undefined,
    };
  });
}

function deriveStepStatus(step: RunStep): string {
  if (step.type === 'error') return 'failed';
  if (step.type === 'tool_result') {
    const success = step.data.success;
    if (typeof success === 'boolean') return success ? 'success' : 'failed';
  }
  if (step.type === 'policy_decision') {
    const decision = step.data.decision;
    if (typeof decision === 'string') return decision;
  }
  const stage = step.data.stage;
  if (typeof stage === 'string' && stage.trim().length > 0) return stage;
  return step.type;
}

function deriveStepDuration(step: RunStep, prevStep?: RunStep, nextStep?: RunStep): number | null {
  const ownDuration = step.data.duration_ms;
  if (typeof ownDuration === 'number' && ownDuration >= 0) return ownDuration;
  if (typeof ownDuration === 'string') {
    const parsed = Number(ownDuration);
    if (!Number.isNaN(parsed) && parsed >= 0) return parsed;
  }
  if (nextStep) {
    const diff = nextStep.timestamp - step.timestamp;
    if (diff >= 0) return diff;
  }
  if (prevStep) {
    const diff = step.timestamp - prevStep.timestamp;
    if (diff >= 0) return diff;
  }
  return null;
}

function renderFieldValue(field: InspectField): JSX.Element {
  const value = field.value;
  if (value === null || value === undefined) return <span className={styles['field-empty']}>—</span>;

  switch (field.type) {
    case 'datetime':
      if (typeof value === 'number' || typeof value === 'string' || value instanceof Date) {
        return <span className={styles['field-value']}>{fmtDateTime(value)}</span>;
      }
      return <pre className={styles['field-json']}>{JSON.stringify(value, null, 2)}</pre>;
    case 'duration':
      if (typeof value === 'number') return <span className={styles['field-value']}>{fmtDuration(value)}</span>;
      if (typeof value === 'string') {
        const parsed = Number(value);
        if (!Number.isNaN(parsed)) return <span className={styles['field-value']}>{fmtDuration(parsed)}</span>;
      }
      return <span className={styles['field-value']}>{String(value)}</span>;
    case 'label':
      return (
        <span className={`${styles['field-label-chip']} ${field.tone ? styles[`field-chip-${field.tone}`] : ''}`}>
          {String(value)}
        </span>
      );
    case 'labels':
      if (!Array.isArray(value)) return <span className={styles['field-value']}>{String(value)}</span>;
      return (
        <div className={styles['field-label-list']}>
          {value.map((item, idx) => (
            <span key={`${field.key}-${idx}`} className={styles['field-label-chip']}>
              {String(item)}
            </span>
          ))}
        </div>
      );
    case 'json':
      return <pre className={styles['field-json']}>{JSON.stringify(value, null, 2)}</pre>;
    case 'bigstring':
      return <pre className={styles['field-bigstring']}>{String(value)}</pre>;
    case 'boolean':
      return (
        <span className={`${styles['field-label-chip']} ${value ? styles['field-chip-success'] : styles['field-chip-neutral']}`}>
          {value ? 'true' : 'false'}
        </span>
      );
    case 'number':
      return <span className={styles['field-value']}>{String(value)}</span>;
    case 'string':
    default:
      return <span className={styles['field-value']}>{String(value)}</span>;
  }
}

function fieldPreview(field: InspectField): string {
  const value = field.value;
  if (value === null || value === undefined) return '—';
  if (field.type === 'datetime' && (typeof value === 'number' || typeof value === 'string')) {
    return fmtDateTime(value);
  }
  if (field.type === 'duration') {
    const n = typeof value === 'number' ? value : Number(value);
    if (!Number.isNaN(n)) return fmtDuration(n);
  }
  if (Array.isArray(value)) return `${value.length} item(s)`;
  if (typeof value === 'object') return 'JSON object';
  const str = String(value);
  return str.length > 72 ? `${str.slice(0, 72)}...` : str;
}

function ParamAccordionList({ fields }: { fields: InspectField[] }) {
  if (fields.length === 0) return <div className={styles['section-empty']}>No data</div>;

  return (
    <div className={styles['param-list']}>
      {fields.map((field, idx) => (
        <details key={field.key} className={styles.param} open={idx === 0}>
          <summary className={styles['param-summary']}>
            <span className={styles['param-label']}>{field.label}</span>
            <span className={styles['param-preview']}>{fieldPreview(field)}</span>
            <span className={styles['section-chevron']}>▾</span>
          </summary>
          <div className={styles['param-body']}>{renderFieldValue(field)}</div>
        </details>
      ))}
    </div>
  );
}

function SectionAccordion({
  title,
  count,
  defaultOpen,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className={styles.section} open={defaultOpen}>
      <summary className={styles['section-summary']}>
        <span className={styles['section-title']}>
          {title}
          {typeof count === 'number' ? ` (${count})` : ''}
        </span>
        <span className={styles['section-chevron']}>▾</span>
      </summary>
      <div className={styles['section-body']}>{children}</div>
    </details>
  );
}

interface Props {
  steps: RunStep[];
  selectedStepId: string | null;
  runStatus?: string;
  runId?: string | null;
}

export default function RunInspector({ steps, selectedStepId, runStatus, runId }: Props) {
  const [activeTab, setActiveTab] = useState<InspectTabKey>('summary');

  const selectedStep = useMemo(
    () => (selectedStepId ? steps.find((s) => s.id === selectedStepId) ?? null : null),
    [steps, selectedStepId],
  );

  const prevStep = useMemo(() => {
    if (!selectedStep) return undefined;
    const idx = steps.indexOf(selectedStep);
    return idx > 0 ? steps[idx - 1] : undefined;
  }, [steps, selectedStep]);

  const nextStep = useMemo(() => {
    if (!selectedStep) return undefined;
    const idx = steps.indexOf(selectedStep);
    return idx >= 0 && idx < steps.length - 1 ? steps[idx + 1] : undefined;
  }, [steps, selectedStep]);

  const meta = selectedStep
    ? STEP_META[selectedStep.type] ?? { label: selectedStep.type, icon: '•', tone: 'neutral' as const }
    : null;

  const summaryFields = useMemo(() => {
    if (!selectedStep) return [];
    const startTs = selectedStep.timestamp;
    const duration = deriveStepDuration(selectedStep, prevStep, nextStep);
    const endTs = duration !== null ? startTs + duration : undefined;
    const status = deriveStepStatus(selectedStep);

    const base: InspectField[] = [
      { key: 'step_type', label: 'Step type', value: selectedStep.type, type: 'label' },
      { key: 'step_title', label: 'Step title', value: getStepTitle(selectedStep), type: 'string' },
      { key: 'status', label: 'Status', value: status, type: 'label', tone: toneFromStatus(status) },
      { key: 'start', label: 'Start', value: startTs, type: 'datetime' },
    ];
    if (endTs !== undefined) base.push({ key: 'end', label: 'End', value: endTs, type: 'datetime' });
    if (duration !== null) base.push({ key: 'duration', label: 'Duration', value: duration, type: 'duration' });

    const highlights = pickRecordByKeys(selectedStep.data, ['stage', 'decision', 'operation', 'tool', 'agent_slug', 'model']);
    return [...base, ...mapToFields(highlights)];
  }, [selectedStep, prevStep, nextStep]);

  const inputFields = useMemo(() => {
    if (!selectedStep) return [];
    const refs = readRefsMap(selectedStep.data.refs);
    const prioritized = pickRecordByKeys(selectedStep.data, INPUT_KEYS);
    const source =
      Object.keys(prioritized).length > 0
        ? prioritized
        : sanitizeSectionRecord(selectedStep.data.input ?? selectedStep.data.payload ?? selectedStep.data.arguments, 'input');
    return mapToFields(source, refs);
  }, [selectedStep]);

  const outputFields = useMemo(() => {
    if (!selectedStep) return [];
    const refs = readRefsMap(selectedStep.data.refs);
    const prioritized = pickRecordByKeys(selectedStep.data, OUTPUT_KEYS);
    const rest = omitKeys(selectedStep.data, [...INPUT_KEYS, ...ERROR_KEYS, ...CONTEXT_KEYS]);
    const fallback = sanitizeSectionRecord(selectedStep.data.output ?? selectedStep.data.result ?? selectedStep.data.response, 'output');
    const source = Object.keys(prioritized).length > 0 ? { ...rest, ...prioritized } : Object.keys(rest).length > 0 ? rest : fallback;
    return mapToFields(source, refs);
  }, [selectedStep]);

  const contextFields = useMemo(() => {
    if (!selectedStep) return [];
    const refs = readRefsMap(selectedStep.data.refs);
    const prioritized = pickRecordByKeys(selectedStep.data, CONTEXT_KEYS);
    delete prioritized.refs;
    const fields = mapToFields(prioritized, refs);

    const resolvedRefLabels = Object.entries(refs)
      .map(([key, value]) => {
        const label = typeof value?.label === 'string' ? value.label.trim() : '';
        if (!label) return null;
        return `${titleFromKey(key)}: ${label}`;
      })
      .filter((value): value is string => Boolean(value));

    if (resolvedRefLabels.length > 0) {
      fields.push({
        key: 'resolved_refs',
        label: 'Связанные сущности',
        value: resolvedRefLabels,
        type: 'labels',
      });
    }
    return fields;
  }, [selectedStep]);

  const errorFields = useMemo(() => {
    if (!selectedStep) return [];
    const prioritized = pickRecordByKeys(selectedStep.data, ERROR_KEYS);
    if (Object.keys(prioritized).length > 0) {
      return mapToFields(prioritized).map((f) => ({ ...f, tone: 'danger' as const }));
    }
    if (selectedStep.type === 'error') {
      return mapToFields(selectedStep.data).map((f) => ({ ...f, tone: 'danger' as const }));
    }
    return [];
  }, [selectedStep]);

  const tabs = useMemo<InspectTabSpec[]>(
    () => [
      { key: 'summary', label: 'Summary', fields: summaryFields },
      { key: 'input', label: 'Input', fields: inputFields },
      { key: 'output', label: 'Output', fields: outputFields },
      { key: 'context', label: 'Context', fields: contextFields },
      { key: 'raw', label: 'Raw', fields: [] },
    ],
    [summaryFields, inputFields, outputFields, contextFields],
  );

  const active = tabs.find((t) => t.key === activeTab) ?? tabs[0];

  if (!selectedStep) {
    return (
      <div className={styles.inspector}>
        <div className={styles.header}>
          <div className={styles['header-left']}>
            <span className={styles.title}>Step inspector</span>
          </div>
        </div>
        <div className={styles.empty}>
          <span>No step selected</span>
          <span className={styles['empty-hint']}>Click a step in chat timeline to inspect details</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.inspector}>
      <div className={styles.header}>
        <div className={styles['header-left']}>
          <span className={styles.title}>Step inspector</span>
          {runId && (
            <span className={styles.subtitle}>
              <span className={`${styles['status-dot']} ${styles[`status-${runStatus ?? 'idle'}`] ?? styles['status-idle']}`} />
              Run {runId.slice(0, 8)}
            </span>
          )}
        </div>
      </div>

      <div className={styles['detail-header']}>
        <div className={styles['detail-title-block']}>
          <span className={styles['detail-label']}>
            {meta?.icon ?? '•'} {meta?.label ?? selectedStep.type}
          </span>
          <span className={styles['detail-title']}>{getStepTitle(selectedStep)}</span>
        </div>
      </div>

      <div className={styles.tabs}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`${styles.tab} ${active.key === tab.key ? styles['tab-active'] : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className={styles.detail}>
        {active.key === 'raw' ? (
          <pre className={styles.payload}>{JSON.stringify(selectedStep.data, null, 2)}</pre>
        ) : (
          <>
            <SectionAccordion title="Parameters" count={active.fields.length} defaultOpen>
              <ParamAccordionList fields={active.fields} />
            </SectionAccordion>
            {active.key === 'summary' ? (
              <SectionAccordion title="Errors" count={errorFields.length} defaultOpen={errorFields.length > 0}>
                <ParamAccordionList fields={errorFields} />
              </SectionAccordion>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

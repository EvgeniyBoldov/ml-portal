/**
 * RunChat — central chat panel showing full conversation chain.
 * Renders all historical runs from branch lineage + current active run.
 * Steps are expandable inline; clicking a step selects it for the right panel.
 */
import { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import Button from '@/shared/ui/Button';
import { Icon } from '@/shared/ui/Icon';
import { Badge, Tooltip } from '@/shared/ui';
import { qk } from '@/shared/api/keys';
import type { ActiveRun, RunStep } from '../hooks/useSandboxRun';
import type { SandboxBranchListItem, SandboxRunListItem } from '../types';
import { normalizeTraceEvent } from '@/domains/runtimeTrace/normalize';
import { sandboxApi } from '../api';
import ChatQuestionCard from './ChatQuestionCard';
import ChatAnswerCard from './ChatAnswerCard';
import styles from './RunChat.module.css';

// ── helpers ──────────────────────────────────────────────────────────────────

const HIDDEN_STEP_TYPES = new Set(['delta', 'final_content', 'done']);

type Tone = 'neutral' | 'info' | 'warn' | 'success' | 'danger';
type BudgetTone = 'neutral' | 'warn' | 'danger';

const CATEGORY_META: Record<string, { icon: string; tone: Tone }> = {
  input: { icon: '◉', tone: 'neutral' },
  budget: { icon: '◷', tone: 'warn' },
  llm: { icon: '◇', tone: 'info' },
  decision: { icon: '🔀', tone: 'info' },
  retry: { icon: '↺', tone: 'warn' },
  operation: { icon: '🔧', tone: 'info' },
  policy: { icon: '🛡', tone: 'warn' },
  planner: { icon: '📐', tone: 'info' },
  final: { icon: '✅', tone: 'success' },
  error: { icon: '❌', tone: 'danger' },
  system: { icon: '•', tone: 'neutral' },
};

function getSemantic(step: RunStep, index: number) {
  return normalizeTraceEvent({
    id: step.id,
    raw_type: step.type,
    data: step.data,
    step_number: index,
    duration_ms: typeof step.data.duration_ms === 'number' ? step.data.duration_ms : undefined,
  });
}

function getStepBadge(step: RunStep, index: number): { text: string; tone: Tone } | null {
  const semantic = getSemantic(step, index);
  if (semantic.status === 'error') return { text: 'ERR', tone: 'danger' };
  if (semantic.status === 'warn') return { text: 'WARN', tone: 'warn' };
  if (semantic.status === 'ok') return { text: 'OK', tone: 'success' };
  return null;
}

type BudgetCompact = {
  key: string;
  label: string;
  used: number;
  limit?: number;
  tone: BudgetTone;
  tooltip: string;
};

type DisplayStep = {
  id: string;
  sourceStepId: string;
  title: string;
  summary: string;
  tone: Tone;
  icon: string;
  elapsedMs: number;
  badge?: { text: string; tone: Tone } | null;
  depth: number;
  budget: BudgetCompact[];
  entity: {
    kind: 'planner' | 'agent' | 'llm' | 'tool_batch' | 'system';
    label: string;
    tone: Tone;
  };
};

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function toNum(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function toneByUsage(used: number, limit?: number): BudgetTone {
  if (typeof limit !== 'number' || limit <= 0) return 'neutral';
  const ratio = used / limit;
  if (ratio >= 0.9) return 'danger';
  if (ratio >= 0.7) return 'warn';
  return 'neutral';
}

function compactBudgetFromData(data: Record<string, unknown>): BudgetCompact[] {
  const shared = toRecord(data.shared_budget ?? data.runtime_budget ?? data.budget);
  const sharedSteps = toRecord(shared.steps);
  const sharedTools = toRecord(shared.tools);
  const sharedRetries = toRecord(shared.retries);
  const sharedTokens = toRecord(shared.tokens);

  const stepsUsed = toNum(sharedSteps.used) ?? toNum(data.steps_used) ?? toNum(data.used) ?? toNum(data.consumed);
  const stepsLimit = toNum(sharedSteps.limit) ?? toNum(data.max_steps) ?? toNum(data.limit);

  const opsUsed =
    toNum(sharedTools.used)
    ?? toNum(data.tool_calls_used)
    ?? toNum(data.operation_calls_total)
    ?? toNum(data.tools_used);
  const opsLimit = toNum(sharedTools.limit) ?? toNum(data.max_tool_calls_total);

  const retriesUsed = toNum(sharedRetries.used) ?? toNum(data.retries_used) ?? toNum(data.retry_count);
  const retriesLimit = toNum(sharedRetries.limit) ?? toNum(data.max_retries);

  const tokensUsed =
    toNum(sharedTokens.used)
    ?? toNum(data.tokens_used)
    ?? toNum(data.tokens_out)
    ?? toNum(data.response_length);
  const tokensLimit = toNum(sharedTokens.limit) ?? toNum(data.max_tokens_total) ?? toNum(data.max_tokens);

  const items: BudgetCompact[] = [];
  if (stepsUsed !== null && (stepsLimit !== null || stepsUsed > 0)) {
    items.push({
      key: 'steps',
      label: 'steps',
      used: stepsUsed,
      limit: stepsLimit ?? undefined,
      tone: toneByUsage(stepsUsed, stepsLimit ?? undefined),
      tooltip: `Шаги: ${stepsUsed}${stepsLimit !== null ? ` / ${stepsLimit}` : ''}`,
    });
  }
  if (opsUsed !== null && (opsLimit !== null || opsUsed > 0)) {
    items.push({
      key: 'ops',
      label: 'ops',
      used: opsUsed,
      limit: opsLimit ?? undefined,
      tone: toneByUsage(opsUsed, opsLimit ?? undefined),
      tooltip: `Операции/инструменты: ${opsUsed}${opsLimit !== null ? ` / ${opsLimit}` : ''}`,
    });
  }
  if (retriesUsed !== null && (retriesLimit !== null || retriesUsed > 0)) {
    items.push({
      key: 'retry',
      label: 'retry',
      used: retriesUsed,
      limit: retriesLimit ?? undefined,
      tone: toneByUsage(retriesUsed, retriesLimit ?? undefined),
      tooltip: `Ретраи: ${retriesUsed}${retriesLimit !== null ? ` / ${retriesLimit}` : ''}`,
    });
  }
  if (tokensUsed !== null && (tokensLimit !== null || tokensUsed > 0)) {
    items.push({
      key: 'tokens',
      label: 'tokens',
      used: tokensUsed,
      limit: tokensLimit ?? undefined,
      tone: toneByUsage(tokensUsed, tokensLimit ?? undefined),
      tooltip: `Токены: ${tokensUsed}${tokensLimit !== null ? ` / ${tokensLimit}` : ''}`,
    });
  }
  return items;
}

function buildDisplaySteps(steps: RunStep[]): DisplayStep[] {
  const result: DisplayStep[] = [];
  let activeAgentSlug = '';
  let pendingToolBatch: {
    firstStepId: string;
    count: number;
    success: number;
    failed: number;
    tools: Set<string>;
    elapsedMs: number;
    budget: BudgetCompact[];
  } | null = null;

  const flushToolBatch = () => {
    if (!pendingToolBatch) return;
    const toolsLabel = Array.from(pendingToolBatch.tools).slice(0, 3).join(', ');
    const truncated = pendingToolBatch.tools.size > 3 ? '…' : '';
    const statusSummary =
      pendingToolBatch.failed > 0
        ? `${pendingToolBatch.success} ok / ${pendingToolBatch.failed} err`
        : `${pendingToolBatch.success} ok`;
    result.push({
      id: `batch_${pendingToolBatch.firstStepId}`,
      sourceStepId: pendingToolBatch.firstStepId,
      title: 'Tool batch',
      summary: `${pendingToolBatch.count} вызов(ов): ${toolsLabel}${truncated} · ${statusSummary}`,
      tone: pendingToolBatch.failed > 0 ? 'warn' : 'info',
      icon: '🧰',
      elapsedMs: pendingToolBatch.elapsedMs,
      badge: pendingToolBatch.failed > 0 ? { text: 'WARN', tone: 'warn' } : null,
      depth: 2,
      budget: pendingToolBatch.budget,
      entity: {
        kind: 'tool_batch',
        label: 'Tool batch',
        tone: pendingToolBatch.failed > 0 ? 'warn' : 'info',
      },
    });
    pendingToolBatch = null;
  };

  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    const semantic = getSemantic(step, index);
    const meta = CATEGORY_META[semantic.category] ?? CATEGORY_META.system;
    const badge = getStepBadge(step, index);
    const elapsed = index > 0 ? Math.max(0, step.timestamp - steps[index - 1].timestamp) : 0;
    const data = toRecord(step.data);
    const budget = compactBudgetFromData(data);

    const isPlannerControl =
      step.type === 'planner_action'
      || step.type === 'planner_step'
      || step.type === 'routing'
      || step.type === 'policy_decision';
    const isToolLike =
      step.type === 'tool_call'
      || step.type === 'tool_result'
      || step.type === 'operation_call'
      || step.type === 'operation_result';
    const isAgentInternal =
      step.type === 'llm_request'
      || step.type === 'llm_call'
      || step.type === 'llm_response'
      || step.type === 'intent'
      || step.type === 'budget_policy'
      || step.type === 'budget_consumed'
      || step.type === 'budget_limit_exceeded'
      || step.type === 'user_request'
      || step.type === 'final_response';

    if (isPlannerControl) {
      flushToolBatch();
      const kind = String(data.kind ?? data.action_type ?? '').toLowerCase();
      const nextAgentSlug = typeof data.agent_slug === 'string' ? data.agent_slug : '';
      if ((kind === 'call_agent' || step.type === 'routing') && nextAgentSlug) {
        activeAgentSlug = nextAgentSlug;
      } else if (kind === 'final' || kind === 'direct_answer' || kind === 'clarify' || kind === 'abort') {
        activeAgentSlug = '';
      }
      result.push({
        id: step.id,
        sourceStepId: step.id,
        title: semantic.title,
        summary: semantic.summary,
        tone: meta.tone,
        icon: meta.icon,
        elapsedMs: elapsed,
        badge,
        depth: 0,
        budget,
        entity: {
          kind: 'planner',
          label: 'Planner',
          tone: 'info',
        },
      });
      continue;
    }

    if (isToolLike && activeAgentSlug) {
      const toolName = String(data.tool ?? data.operation_slug ?? data.operation ?? 'tool');
      const isSuccess = data.success === true;
      const isFailed = data.success === false;
      if (!pendingToolBatch) {
        pendingToolBatch = {
          firstStepId: step.id,
          count: 0,
          success: 0,
          failed: 0,
          tools: new Set<string>(),
          elapsedMs: 0,
          budget: [],
        };
      }
      pendingToolBatch.count += 1;
      pendingToolBatch.tools.add(toolName);
      if (isSuccess) pendingToolBatch.success += 1;
      if (isFailed) pendingToolBatch.failed += 1;
      pendingToolBatch.elapsedMs += elapsed;
      if (budget.length > 0) pendingToolBatch.budget = budget;
      continue;
    }

    flushToolBatch();

    const depth = activeAgentSlug && (isAgentInternal || isToolLike) ? 1 : 0;
    const isLlmStep =
      step.type === 'llm_request'
      || step.type === 'llm_call'
      || step.type === 'llm_response';
    const entity =
      depth === 0
        ? { kind: 'system' as const, label: 'Runtime', tone: 'neutral' as Tone }
        : isLlmStep
          ? { kind: 'llm' as const, label: 'LLM', tone: 'info' as Tone }
          : { kind: 'agent' as const, label: activeAgentSlug ? `Agent:${activeAgentSlug}` : 'Agent', tone: 'info' as Tone };
    result.push({
      id: step.id,
      sourceStepId: step.id,
      title: semantic.title,
      summary: semantic.summary,
      tone: meta.tone,
      icon: meta.icon,
      elapsedMs: elapsed,
      badge,
      depth,
      budget,
      entity,
    });
  }

  flushToolBatch();
  return result;
}

function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function extractFinalContent(
  steps: Array<{ step_type: string; step_data: Record<string, unknown> }>,
): string {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.step_type === 'final' || step.step_type === 'final_content') {
      const content = step.step_data.content;
      if (typeof content === 'string') return content;
    }
  }
  let result = '';
  for (const step of steps) {
    if (step.step_type === 'delta' && typeof step.step_data.content === 'string') {
      result += step.step_data.content;
    }
  }
  return result;
}

function apiStepsToRunSteps(
  apiSteps: Array<{ id: string; step_type: string; step_data: Record<string, unknown>; created_at: string }>,
): RunStep[] {
  return apiSteps.map((s) => ({
    id: s.id,
    type: s.step_type as RunStep['type'],
    data: s.step_data,
    timestamp: new Date(s.created_at).getTime(),
  }));
}

function buildToolSummary(steps: RunStep[]): Map<string, number> {
  const tools = new Map<string, number>();
  for (const s of steps) {
    if (s.type === 'tool_call') {
      const tool = (s.data.tool as string) ?? '?';
      tools.set(tool, (tools.get(tool) ?? 0) + 1);
    }
  }
  return tools;
}

function getVisibleSteps(steps: RunStep[]): RunStep[] {
  return steps.filter((s) => !HIDDEN_STEP_TYPES.has(s.type));
}

// ── ExpandableSteps — inline step list in chat ────────────────────────────

function ExpandableSteps({
  steps,
  isRunning,
  selectedStepId,
  onSelectStep,
}: {
  steps: RunStep[];
  isRunning: boolean;
  selectedStepId: string | null;
  onSelectStep: (stepId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = useMemo(() => getVisibleSteps(steps), [steps]);
  const displaySteps = useMemo(() => buildDisplaySteps(visible), [visible]);
  const toolCalls = useMemo(() => buildToolSummary(steps), [steps]);
  const totalDuration = useMemo(() => {
    if (steps.length < 2) return null;
    const diff = steps[steps.length - 1].timestamp - steps[0].timestamp;
    return diff > 0 ? fmtDuration(diff) : null;
  }, [steps]);

  if (displaySteps.length === 0 && !isRunning) return null;

  return (
    <div className={styles['steps-block']}>
      <button
        type="button"
        className={`${styles['steps-summary']} ${expanded ? styles['steps-summary-expanded'] : ''}`}
        onClick={() => setExpanded((p) => !p)}
        aria-expanded={expanded}
        aria-label="Развернуть шаги"
      >
        <span className={styles['steps-summary-icon']}>
          {isRunning ? '◎' : '✓'}
        </span>
        <span className={styles['steps-summary-text']}>
          {visible.length} шагов
        </span>
        {totalDuration && (
          <span className={styles['steps-summary-duration']}>{totalDuration}</span>
        )}
        {Array.from(toolCalls.entries()).map(([tool, count]) => (
          <span key={tool} className={styles['steps-summary-tag']}>
            {tool} ×{count}
          </span>
        ))}
        {isRunning && (
          <span className={styles['steps-summary-running']}>выполняется...</span>
        )}
        <span className={`${styles['steps-summary-chevron']} ${expanded ? styles['steps-summary-chevron-open'] : ''}`}>
          ▾
        </span>
      </button>

      {expanded && (
        <div className={styles['steps-list']}>
          {displaySteps.map((item) => {
            const isSelected = item.sourceStepId === selectedStepId;

            return (
              <button
                key={item.id}
                type="button"
                className={`${styles['step-row']} ${isSelected ? styles['step-row-selected'] : ''}`}
                onClick={() => onSelectStep(item.sourceStepId)}
                style={{ paddingLeft: `${8 + item.depth * 18}px` }}
              >
                <span className={`${styles['step-tone']} ${styles[`tone-${item.tone}`]}`} />
                <span className={styles['step-icon']}>{item.icon}</span>
                <span className={`${styles['step-entity']} ${styles[`step-entity-${item.entity.tone}`]}`}>
                  {item.entity.label}
                </span>
                <span className={styles['step-label']}>{item.title}</span>
                <span className={styles['step-title']}>{item.summary}</span>
                {item.elapsedMs > 50 && (
                  <span className={styles['step-elapsed']}>+{fmtDuration(item.elapsedMs)}</span>
                )}
                {item.budget.map((metric) => (
                  <Tooltip key={`${item.id}_${metric.key}`} content={metric.tooltip} position="top" maxWidth={260}>
                    <span>
                      <Badge tone={metric.tone === 'danger' ? 'danger' : metric.tone === 'warn' ? 'warn' : 'neutral'} size="sm">
                        {metric.used}{typeof metric.limit === 'number' ? `/${metric.limit}` : ''}
                      </Badge>
                    </span>
                  </Tooltip>
                ))}
                {item.badge && (
                  <span className={`${styles['step-badge']} ${styles[`badge-${item.badge.tone}`]}`}>
                    {item.badge.text}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── HistoricalRunItem ───────────────────────────────────────────────────────

function HistoricalRunItem({
  sessionId,
  run,
  branch,
  isCurrentBranch,
  isReadOnly,
  selectedStepId,
  onSelectStep,
  onForkBranch,
}: {
  sessionId: string;
  run: SandboxRunListItem;
  branch?: SandboxBranchListItem;
  isCurrentBranch: boolean;
  isReadOnly: boolean;
  selectedStepId: string | null;
  onSelectStep: (runId: string, stepId: string, steps: RunStep[]) => void;
  onForkBranch: (runId: string, sourceText: string) => void;
}) {
  const { data: runDetail } = useQuery({
    queryKey: qk.sandbox.runs.detail(sessionId, run.id),
    queryFn: () => sandboxApi.getRunDetail(sessionId, run.id),
    enabled: run.status !== 'running',
    staleTime: 60_000,
  });

  const finalContent = runDetail ? extractFinalContent(runDetail.steps) : '';
  const isFailed = run.status === 'failed';

  const runSteps = useMemo(
    () => (runDetail ? apiStepsToRunSteps(runDetail.steps) : []),
    [runDetail],
  );

  return (
    <div className={styles['conversation-item']}>
      <div className={styles['question-row']}>
        <ChatQuestionCard text={run.request_text} />
      </div>

      {!isCurrentBranch && branch && (
        <span className={styles['branch-label']}>от ветки: {branch.name}</span>
      )}

      <ExpandableSteps
        steps={runSteps}
        isRunning={false}
        selectedStepId={selectedStepId}
        onSelectStep={(stepId) => onSelectStep(run.id, stepId, runSteps)}
      />

      <div className={styles['answer-row']}>
        {runDetail ? (
          <ChatAnswerCard
            text={isFailed ? (runDetail.error ?? 'Ошибка выполнения') : finalContent}
            isRunning={false}
          />
        ) : (
          <div className={styles['answer-loading']}>Загрузка ответа...</div>
        )}
        {!isReadOnly && (
          <button
            type="button"
            className={styles['fork-btn']}
            title="Создать ветку от этого ответа"
            onClick={() => onForkBranch(run.id, run.request_text)}
          >
            ⑂
          </button>
        )}
      </div>
    </div>
  );
}

// ── Props ────────────────────────────────────────────────────────────────────

interface Props {
  sessionId: string;
  branches: SandboxBranchListItem[];
  activeBranchId: string;
  branchRuns: SandboxRunListItem[];
  activeRun: ActiveRun;
  isRunning: boolean;
  isWaitingInput?: boolean;
  isReadOnly: boolean;
  isCreatingBranch?: boolean;
  onSelectBranch: (branchId: string) => void;
  onCreateBranchFromMessage: (sourceText: string, parentRunId?: string | null) => Promise<void>;
  onRun: (text: string, parentRunId?: string | null, attachmentIds?: string[]) => void;
  onStop: () => void;
  onSelectRun?: (runId?: string) => void;
  onSelectStep?: (runId: string, stepId: string, steps: RunStep[]) => void;
}

// ── RunChat ──────────────────────────────────────────────────────────────────

export default function RunChat({
  sessionId,
  branches,
  activeBranchId,
  branchRuns,
  activeRun,
  isRunning,
  isWaitingInput = false,
  isReadOnly,
  isCreatingBranch = false,
  onSelectBranch,
  onCreateBranchFromMessage,
  onRun,
  onStop,
  onSelectRun,
  onSelectStep,
}: Props) {
  type PendingAttachment = { id: string; file: File };
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPolicy, setUploadPolicy] = useState<{
    max_bytes: number;
    allowed_extensions: string[];
    allowed_content_types_by_extension?: Record<string, string[]>;
  } | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const clarifyInputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const branchMap = useMemo(
    () => new Map(branches.map((b) => [b.id, b])),
    [branches],
  );

  const branchLineage = useMemo(() => {
    const lineage: SandboxBranchListItem[] = [];
    const seen = new Set<string>();
    let current = branchMap.get(activeBranchId);
    while (current && !seen.has(current.id)) {
      lineage.push(current);
      seen.add(current.id);
      current = current.parent_branch_id ? branchMap.get(current.parent_branch_id) : undefined;
    }
    return lineage;
  }, [activeBranchId, branchMap]);

  const lineageBranchIds = useMemo(
    () => new Set(branchLineage.map((b) => b.id)),
    [branchLineage],
  );

  const lineageRuns = useMemo(
    () =>
      branchRuns
        .filter((run) => run.branch_id && lineageBranchIds.has(run.branch_id))
        .sort((a, b) => a.started_at.localeCompare(b.started_at)),
    [branchRuns, lineageBranchIds],
  );

  const historicalRuns = useMemo(
    () => lineageRuns.filter((run) => run.id !== activeRun.runId),
    [lineageRuns, activeRun.runId],
  );

  useEffect(() => {
    setInput('');
    setSelectedStepId(null);
  }, [activeBranchId]);

  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeRun.steps.length, historicalRuns.length]);

  useEffect(() => {
    if (isWaitingInput && !isRunning) {
      clarifyInputRef.current?.focus();
    }
  }, [isWaitingInput, isRunning]);

  useEffect(() => {
    let mounted = true;
    import('@/shared/api/chats')
      .then(({ getChatUploadPolicy }) => getChatUploadPolicy())
      .then((policy) => {
        if (mounted) setUploadPolicy(policy);
      })
      .catch(() => {
        if (mounted) setUploadPolicy(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = async () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || isRunning || isReadOnly || isUploading) return;

    let attachmentIds: string[] = [];
    if (attachments.length > 0) {
      try {
        setIsUploading(true);
        const uploaded = await Promise.all(
          attachments.map((item) => sandboxApi.uploadAttachment(sessionId, item.file))
        );
        attachmentIds = uploaded.map((item) => item.id);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Ошибка загрузки файла');
        setIsUploading(false);
        return;
      }
    }

    setInput('');
    setAttachments([]);
    setUploadError(null);
    setIsUploading(false);
    onRun(text, isWaitingInput ? activeRun.runId : undefined, attachmentIds);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    const maxBytes = uploadPolicy?.max_bytes ?? 50 * 1024 * 1024;
    const allowedExtensions = new Set(
      (uploadPolicy?.allowed_extensions ?? ['txt', 'md', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'])
        .map((item) => item.toLowerCase().replace(/^\./, ''))
    );
    const validFiles: File[] = [];
    const allowedMimeByExt = uploadPolicy?.allowed_content_types_by_extension ?? {};
    for (const file of files) {
      const fileName = (file.name || '').toLowerCase();
      const dotIdx = fileName.lastIndexOf('.');
      const ext = dotIdx >= 0 ? fileName.slice(dotIdx + 1) : '';
      if (!ext || !allowedExtensions.has(ext)) {
        setUploadError(`Файл "${file.name}" не поддерживается`);
        continue;
      }
      if (file.size > maxBytes) {
        setUploadError(`Файл "${file.name}" превышает лимит ${(maxBytes / 1024 / 1024).toFixed(0)} МБ`);
        continue;
      }
      const allowedMime = allowedMimeByExt[ext];
      const mime = (file.type || '').toLowerCase();
      if (mime && Array.isArray(allowedMime) && allowedMime.length > 0 && !allowedMime.includes(mime)) {
        setUploadError(`Файл "${file.name}" имеет неподдерживаемый MIME: ${mime}`);
        continue;
      }
      validFiles.push(file);
    }

    if (!validFiles.length) {
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    setUploadError(null);
    setAttachments((prev) => [
      ...prev,
      ...validFiles.map((file) => ({ id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, file })),
    ]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((item) => item.id !== id));
  };

  const acceptValue = useMemo(() => {
    const list = uploadPolicy?.allowed_extensions ?? ['txt', 'md', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'];
    return list.map((ext) => (ext.startsWith('.') ? ext : `.${ext}`)).join(',');
  }, [uploadPolicy]);

  const handleSubmitVoid = () => {
    void handleSubmit();
  };

  const handleClarifySubmit = () => {
    const text = input.trim();
    if (!text || attachments.length > 0) return;
    onRun(text, isWaitingInput ? activeRun.runId : undefined);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmitVoid();
    }
  };

  const handleSelectStep = (runId: string, stepId: string, steps: RunStep[]) => {
    setSelectedStepId(stepId);
    onSelectRun?.(runId);
    onSelectStep?.(runId, stepId, steps);
  };

  const handleSelectActiveStep = (stepId: string) => {
    setSelectedStepId(stepId);
    onSelectRun?.();
    onSelectStep?.('active', stepId, activeRun.steps);
  };

  const handleForkBranch = (parentRunId: string, sourceText: string) => {
    if (isCreatingBranch) return;
    void onCreateBranchFromMessage(sourceText, parentRunId).then(() => {
      setInput(sourceText);
    });
  };

  const handleForkFromActive = () => {
    const runListItem = lineageRuns.find((r) => r.id === activeRun.runId);
    const sourceText = runListItem?.request_text ?? input;
    if (!sourceText.trim() || isCreatingBranch) return;
    void onCreateBranchFromMessage(sourceText, activeRun.runId).then(() => {
      setInput(sourceText);
    });
  };

  const hasActiveRun = activeRun.status !== 'idle';
  const hasHistory = historicalRuns.length > 0;
  const showActiveAnswerCard = isRunning || activeRun.finalContent.trim().length > 0;
  const latestClarifyQuestion = useMemo(() => {
    for (let i = activeRun.steps.length - 1; i >= 0; i--) {
      const step = activeRun.steps[i];
      if (step.type === 'waiting_input') {
        const q = step.data.question;
        if (typeof q === 'string' && q.trim().length > 0) return q;
      }
      if (step.type === 'stop') {
        const q = step.data.question ?? step.data.message;
        if (typeof q === 'string' && q.trim().length > 0) return q;
      }
    }
    return null;
  }, [activeRun.steps]);

  const activeUserMessage = useMemo(() => {
    const fromRun = String(activeRun.requestText || '').trim();
    if (fromRun) return fromRun;
    const fromLineage = String(lineageRuns.find((r) => r.id === activeRun.runId)?.request_text || '').trim();
    if (fromLineage) return fromLineage;
    return input.trim();
  }, [activeRun.requestText, activeRun.runId, lineageRuns, input]);

  const activeAssistantMessage = useMemo(() => {
    const finalText = String(activeRun.finalContent || '').trim();
    if (finalText) return finalText;
    if (isWaitingInput && latestClarifyQuestion) return latestClarifyQuestion;
    return '';
  }, [activeRun.finalContent, isWaitingInput, latestClarifyQuestion]);

  return (
    <div className={styles.chat}>
      <div className={styles.messages} ref={messagesRef}>
        {!hasHistory && !hasActiveRun && (
          <div className={styles['empty-chat']}>
            <div className={styles['empty-title']}>Sandbox</div>
            <div className={styles['empty-hint']}>
              Введите запрос и запустите агента с текущими оверрайдами.
              Каждый вызов инструмента записи потребует подтверждения.
            </div>
          </div>
        )}

        {historicalRuns.map((run) => (
          <HistoricalRunItem
            key={run.id}
            sessionId={sessionId}
            run={run}
            branch={run.branch_id ? branchMap.get(run.branch_id) : undefined}
            isCurrentBranch={run.branch_id === activeBranchId}
            isReadOnly={isReadOnly}
            selectedStepId={selectedStepId}
            onSelectStep={handleSelectStep}
            onForkBranch={handleForkBranch}
          />
        ))}

        {hasActiveRun && (
          <div className={styles['conversation-item']}>
            <div className={styles['question-row']}>
              <ChatQuestionCard text={activeUserMessage} />
            </div>

            <ExpandableSteps
              steps={activeRun.steps}
              isRunning={isRunning}
              selectedStepId={selectedStepId}
              onSelectStep={handleSelectActiveStep}
            />

            <div className={styles['answer-row']}>
              {(showActiveAnswerCard || (isWaitingInput && !!latestClarifyQuestion)) && (
                <ChatAnswerCard text={activeAssistantMessage} isRunning={isRunning} />
              )}
              {!isReadOnly && !isRunning && activeRun.finalContent && (
                <button
                  type="button"
                  className={styles['fork-btn']}
                  title="Создать ветку от этого ответа"
                  onClick={handleForkFromActive}
                >
                  ⑂
                </button>
              )}
            </div>

            {!isReadOnly && isWaitingInput && (
              <div className={styles['clarify-box']}>
                <div className={styles['clarify-title']}>Нужно уточнение от пользователя</div>
                <div className={styles['clarify-row']}>
                  <textarea
                    ref={clarifyInputRef}
                    className={styles['input-field']}
                    placeholder="Введите уточнение для продолжения..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={2}
                    disabled={isRunning}
                  />
                  <Button
                    size="sm"
                    onClick={handleClarifySubmit}
                    disabled={!input.trim() || isRunning || attachments.length > 0}
                  >
                    Ответить
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {!isReadOnly && (
        <div className={styles['input-area']}>
          <div className={styles['branch-tabs-shell']}>
            <div className={styles['branch-tabs']} role="tablist" aria-label="Ветки чата">
              {branches.map((branch) => {
                const isActive = activeBranchId === branch.id;
                const runCount = branchRuns.filter((r) => r.branch_id === branch.id).length;
                return (
                  <button
                    key={branch.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    className={`${styles['branch-tab']} ${isActive ? styles['branch-tab-active'] : ''}`}
                    onClick={() => onSelectBranch(branch.id)}
                  >
                    {branch.name} · {runCount}
                  </button>
                );
              })}
            </div>
          </div>
          <div className={styles['input-row']}>
            <button
              type="button"
              className={styles['upload-btn']}
              title="Добавить файл"
              onClick={() => fileInputRef.current?.click()}
              disabled={isRunning || isUploading || isWaitingInput}
            >
              <Icon name="plus" size={16} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileSelect}
              className={styles['file-input']}
              accept={acceptValue}
            />
            <textarea
              className={styles['input-field']}
              placeholder={isWaitingInput ? 'Введите уточнение для продолжения...' : 'Введите запрос для агента...'}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isRunning || isUploading}
            />
            {isRunning ? (
              <Button size="sm" variant="danger" onClick={onStop}>
                Стоп
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={isWaitingInput ? handleClarifySubmit : handleSubmitVoid}
                disabled={isWaitingInput ? !input.trim() : (!input.trim() && attachments.length === 0) || isUploading}
              >
                {isUploading ? 'Загрузка...' : (isWaitingInput ? 'Ответить' : 'Запуск')}
              </Button>
            )}
          </div>
          {attachments.length > 0 && (
            <div className={styles.attachments}>
              {attachments.map((item) => (
                <div key={item.id} className={styles.attachment}>
                  <div className={styles.attachmentIcon}>
                    <Icon name="file" size={14} />
                  </div>
                  <span className={styles.attachmentName}>{item.file.name}</span>
                  <button type="button" className={styles.attachmentRemove} onClick={() => removeAttachment(item.id)}>
                    <Icon name="x" size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
          {uploadError && <div className={styles['upload-error']}>{uploadError}</div>}
        </div>
      )}
    </div>
  );
}

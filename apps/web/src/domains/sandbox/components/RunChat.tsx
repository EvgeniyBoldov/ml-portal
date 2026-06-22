/**
 * RunChat — central chat panel showing full conversation chain.
 * Renders all historical runs from branch lineage + current active run.
 * Steps are expandable inline; clicking a step selects it for the right panel.
 */
import { useState, useRef, useEffect, useMemo, type ChangeEvent, type KeyboardEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import Button from '@/shared/ui/Button';
import { Icon } from '@/shared/ui/Icon';
import { Badge, Tooltip } from '@/shared/ui';
import { qk } from '@/shared/api/keys';
import type { ActiveRun, RunStep } from '../hooks/useSandboxRun';
import type { SandboxBranchListItem, SandboxRunListItem } from '../types';
import { normalizeTraceEvent } from '@/domains/runtimeTrace/normalize';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { sandboxApi } from '../api';
import type { ExecutionMode } from '@/shared/api/types';
import ChatQuestionCard from './ChatQuestionCard';
import ChatAnswerCard from './ChatAnswerCard';
import { TraceSteps } from './TraceSteps';
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
  system: { icon: '', tone: 'neutral' },
};

function getSemantic(step: RunStep, index: number) {
  return normalizeTraceEvent({
    id: step.id,
    raw_type: step.type,
    data: step.data,
    step_number: step.orderNumber ?? index,
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

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function fmtDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1).replace('.', ',')} s`;
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
  apiSteps: Array<{ id: string; step_type: string; step_data: Record<string, unknown>; created_at: string; order_num?: number }>,
): RunStep[] {
  return apiSteps.map((s) => ({
    id: s.id,
    type: s.step_type as RunStep['type'],
    data: s.step_data,
    timestamp: new Date(s.created_at).getTime(),
    orderNumber: typeof s.order_num === 'number' ? s.order_num : undefined,
  }));
}

function buildToolSummary(steps: RunStep[]): Map<string, number> {
  const tools = new Map<string, number>();
  for (const s of steps) {
    if (s.type === 'tool_call' || s.type === 'tool_result' || s.type === 'operation_result') {
      const tool = (s.data.tool as string) ?? (s.data.operation_slug as string) ?? '?';
      tools.set(tool, (tools.get(tool) ?? 0) + 1);
    }
  }
  return tools;
}

// ── ExpandableSteps — inline step list in chat ────────────────────────────

function ExpandableSteps({
  steps,
  isRunning,
  selectedDisplayStepId,
  onSelectStep,
}: {
  steps: RunStep[];
  isRunning: boolean;
  selectedDisplayStepId: string | null;
  onSelectStep: (displayStepId: string, rawStepId: string, inspectorSteps: RunStep[], entity?: TraceEntity) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const toolCalls = useMemo(() => buildToolSummary(steps), [steps]);
  const totalDuration = useMemo(() => {
    if (steps.length < 2) return null;
    const diff = steps[steps.length - 1].timestamp - steps[0].timestamp;
    return diff > 0 ? fmtDuration(diff) : null;
  }, [steps]);

  // Filter visible steps (hide delta, final_content, done)
  const visibleSteps = useMemo(() => steps.filter((s) => !HIDDEN_STEP_TYPES.has(s.type)), [steps]);

  if (visibleSteps.length === 0 && !isRunning) return null;

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
          {visibleSteps.length} шагов
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
          <TraceSteps
            steps={visibleSteps}
            isRunning={isRunning}
            selectedEntityId={selectedDisplayStepId}
            onSelectEntity={(entity) => {
              const sourceStepId = entity.sourceEventIds[0] ?? entity.id;
              onSelectStep(entity.id, sourceStepId, visibleSteps, entity);
            }}
          />
        </div>
      )}
    </div>
  );
}

// ── HistoricalRunItem ───────────────────────────────────────────────────────

interface HistoricalRunItemProps {
  sessionId: string;
  run: SandboxRunListItem;
  branch?: SandboxBranchListItem;
  isCurrentBranch: boolean;
  isReadOnly: boolean;
  selectedDisplayStepId: string | null;
  onSelectStep: (
    runId: string,
    displayStepId: string,
    rawStepId: string,
    steps: RunStep[],
    entity?: TraceEntity,
  ) => void;
  onForkBranch: (runId: string, sourceText: string) => void;
}

function HistoricalRunItem(props: HistoricalRunItemProps) {
  const {
    sessionId,
    run,
    branch,
    isCurrentBranch,
    isReadOnly,
    selectedDisplayStepId,
    onSelectStep,
    onForkBranch,
  } = props;
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
        selectedDisplayStepId={selectedDisplayStepId}
        onSelectStep={(displayStepId, rawStepId, inspectorSteps, entity) => 
          onSelectStep(run.id, displayStepId, rawStepId, inspectorSteps, entity)
        }
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
  onRun: (text: string, parentRunId?: string | null, attachmentIds?: string[], executionMode?: ExecutionMode) => void;
  onResumeSubmit: (text: string) => void;
  onStop: () => void;
  onSelectRun?: (runId?: string) => void;
  onSelectStep?: (runId: string, stepId: string, steps: RunStep[], entity?: TraceEntity) => void;
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
  onResumeSubmit,
  onStop,
  onSelectRun,
  onSelectStep,
}: Props) {
  type PendingAttachment = { id: string; file: File };
  const [input, setInput] = useState('');
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('normal');
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPolicy, setUploadPolicy] = useState<{
    max_bytes: number;
    allowed_extensions: string[];
    allowed_content_types_by_extension?: Record<string, string[]>;
  } | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedDisplayStepId, setSelectedDisplayStepId] = useState<string | null>(null);
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
    setSelectedDisplayStepId(null);
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
    if (isWaitingInput || activeRun.status === 'waiting_confirmation') return;
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
    onRun(text, isWaitingInput ? activeRun.runId : undefined, attachmentIds, executionMode);
  };

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
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
    if (!text) return;
    setInput('');
    onResumeSubmit(text);
  };

  const handleComposerKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmitVoid();
    }
  };

  const handleClarifyKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleClarifySubmit();
    }
  };

  const handleSelectStep = (
    runId: string,
    displayStepId: string,
    rawStepId: string,
    steps: RunStep[],
    entity?: TraceEntity,
  ) => {
    setSelectedDisplayStepId(displayStepId);
    setSelectedStepId(rawStepId);
    onSelectStep?.(runId, rawStepId, steps, entity);
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
  const isPaused = activeRun.status === 'waiting_input' || activeRun.status === 'waiting_confirmation';
  const showActiveAnswerCard = !isPaused && (isRunning || activeRun.finalContent.trim().length > 0);
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
    return String(activeRun.finalContent || '').trim();
  }, [activeRun.finalContent]);

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
            selectedDisplayStepId={selectedDisplayStepId}
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
              selectedDisplayStepId={selectedDisplayStepId}
              onSelectStep={(displayStepId, rawStepId, inspectorSteps, entity) => {
                setSelectedDisplayStepId(displayStepId);
                setSelectedStepId(rawStepId);
                onSelectStep?.('active', rawStepId, inspectorSteps, entity);
              }}
            />

            <div className={styles['answer-row']}>
              {showActiveAnswerCard && (
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

            {!isReadOnly && (isWaitingInput || activeRun?.status === 'waiting_confirmation') && (
              <div className={styles['clarify-box']}>
                <div className={styles['clarify-title']}>
                  {isWaitingInput
                    ? (latestClarifyQuestion || 'Нужно уточнение от пользователя')
                    : (String((activeRun?.pendingConfirmation as Record<string, unknown> | null)?.summary || '')
                      || String((activeRun?.pendingConfirmation as Record<string, unknown> | null)?.message || '')
                      || 'Требуется подтверждение')}
                </div>
                <div className={styles['clarify-row']}>
                  <textarea
                    ref={clarifyInputRef}
                    className={styles['input-field']}
                    placeholder="Введите уточнение для продолжения..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleClarifyKeyDown}
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

      {!isReadOnly && !isPaused && (
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
            <select
              className={styles['mode-select']}
              value={executionMode}
              onChange={(e) => setExecutionMode(e.target.value as ExecutionMode)}
              disabled={isRunning || isUploading || isWaitingInput}
              aria-label="Execution mode"
            >
              <option value="normal">Normal</option>
              <option value="thinking">Thinking</option>
            </select>
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
              onKeyDown={handleComposerKeyDown}
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

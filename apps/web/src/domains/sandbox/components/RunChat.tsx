/**
 * RunChat — central chat panel showing full conversation chain.
 * Renders all historical runs from branch lineage + current active run.
 * Steps are expandable inline; clicking a step selects it for the right panel.
 */
import { useState, useRef, useEffect, useMemo, type ChangeEvent, type KeyboardEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import Button from '@/shared/ui/Button';
import { Icon } from '@/shared/ui/Icon';
import { Tooltip } from '@/shared/ui';
import { qk } from '@/shared/api/keys';
import type { ActiveRun } from '../hooks/useSandboxRun';
import type { SandboxBranchListItem, SandboxRunListItem, RuntimeJournalEvent } from '../types';
import { replayRuntimeJournal } from '../traceState';
import { sandboxApi } from '../api';
import ChatQuestionCard from './ChatQuestionCard';
import ChatAnswerCard from './ChatAnswerCard';
import { ExecutionTrace } from './ExecutionTrace';
import type { TraceInspectionTarget } from '../traceProjection';
import styles from './RunChat.module.css';

// ── helpers ──────────────────────────────────────────────────────────────────

function extractClarifyQuestion(context: Record<string, unknown> | undefined): string | null {
  const question = context && typeof context.question === 'string' ? context.question.trim() : '';
  return question || null;
}

function extractFinalContent(
  events: RuntimeJournalEvent[],
): string {
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    if (event.event_type === 'final' || event.event_type === 'final_content') {
      const content = event.payload.content;
      if (typeof content === 'string') return content;
    }
  }
  let result = '';
  for (const event of events) {
    if (event.event_type === 'delta' && typeof event.payload.content === 'string') {
      result += event.payload.content;
    }
  }
  return result;
}

// ── HistoricalRunItem ───────────────────────────────────────────────────────

interface HistoricalRunItemProps {
  sessionId: string;
  run: SandboxRunListItem;
  branch?: SandboxBranchListItem;
  isCurrentBranch: boolean;
  isReadOnly: boolean;
  onForkBranch: (runId: string, sourceText: string) => void;
  onSelectTraceTarget?: (target: TraceInspectionTarget, trace: ReturnType<typeof replayRuntimeJournal>) => void;
  selectedTraceTargetKey?: string | null;
}

function HistoricalRunItem(props: HistoricalRunItemProps) {
  const {
    sessionId,
    run,
    branch,
    isCurrentBranch,
    isReadOnly,
    onForkBranch,
    onSelectTraceTarget,
    selectedTraceTargetKey,
  } = props;
  const { data: runDetail } = useQuery({
    queryKey: qk.sandbox.runs.detail(sessionId, run.id),
    queryFn: () => sandboxApi.getRunDetail(sessionId, run.id),
    enabled: true,
    staleTime: 60_000,
    refetchInterval: run.status === 'running' ? 2_000 : false,
  });

  const finalContent = runDetail ? extractFinalContent(runDetail.events) : '';
  const isFailed = run.status === 'failed';

  const trace = useMemo(
    () => replayRuntimeJournal(runDetail?.events ?? []),
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

      <ExecutionTrace trace={trace} isRunning={false} onSelectTarget={(target) => onSelectTraceTarget?.(target, trace)} selectedTargetKey={selectedTraceTargetKey} />

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
  onRun: (text: string, parentRunId?: string | null, artifactIds?: string[]) => void;
  onResumeSubmit: (text: string) => void;
  onStop: () => void;
  onSelectRun?: (runId?: string) => void;
  onSelectTraceTarget?: (target: TraceInspectionTarget, trace: ReturnType<typeof replayRuntimeJournal>) => void;
  selectedTraceTargetKey?: string | null;
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
  onSelectTraceTarget,
  selectedTraceTargetKey,
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
  }, [activeBranchId]);

  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeRun.trace.eventIdsBySequence.length, activeRun.progress.length, historicalRuns.length]);

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

    let artifactIds: string[] = [];
    if (attachments.length > 0) {
      try {
        setIsUploading(true);
        const uploaded = await Promise.all(
          attachments.map((item) => sandboxApi.uploadAttachment(sessionId, item.file))
        );
        artifactIds = uploaded.map((item) => item.artifact_id);
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
    onRun(text, isWaitingInput ? activeRun.runId : undefined, artifactIds);
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
  const latestClarifyQuestion = useMemo(
    () => extractClarifyQuestion(activeRun.pendingConfirmation?.context),
    [activeRun.pendingConfirmation],
  );

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
            onForkBranch={handleForkBranch}
            onSelectTraceTarget={onSelectTraceTarget}
            selectedTraceTargetKey={selectedTraceTargetKey}
          />
        ))}

        {hasActiveRun && (
          <div className={styles['conversation-item']}>
            <div className={styles['question-row']}>
              <ChatQuestionCard text={activeUserMessage} />
            </div>

            <ExecutionTrace trace={activeRun.trace} isRunning={isRunning} progress={activeRun.progress} onSelectTarget={(target) => onSelectTraceTarget?.(target, activeRun.trace)} selectedTargetKey={selectedTraceTargetKey} />

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
                    : (String(activeRun?.pendingConfirmation?.context.summary || '')
                      || String(activeRun?.pendingConfirmation?.context.message || '')
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

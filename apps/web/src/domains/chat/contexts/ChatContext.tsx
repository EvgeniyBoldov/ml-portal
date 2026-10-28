import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  ReactNode,
  useMemo,
} from 'react';
import type { ChatPausedRun } from '@/shared/api/chats';
import type { ActiveChatRun, ChatHistory, ChatTimelineMessage } from '../types';
import { toRenderableMessage } from '../chatMessages';
import { useChatStreaming } from '../hooks/useChatStreaming';

type Message = ChatTimelineMessage;

interface PendingConfirmation {
  operationFingerprint: string;
  toolSlug: string;
  operation: string;
  riskLevel: string;
  argsPreview: string;
  question: string;
  summary: string;
  runId?: string | null;
}

interface PendingInput {
  question?: string;
  reason?: string;
}

interface ResumePausedState {
  runId?: string | null;
  reason?: string | null;
  question?: string | null;
  message?: string | null;
  action?: Record<string, unknown> | null;
  interaction?: Record<string, unknown>;
}

interface ChatState {
  messagesByChat: Record<string, ChatHistory>;
  activeRun: ActiveChatRun | null;
  pendingConfirmations: PendingConfirmation[];
  pendingInput: PendingInput | null;
  pausedRunId: string | null;
  hasInteraction: boolean;
  isStreaming: boolean;
}

interface ChatActions {
  loadMessages: (chatId: string) => Promise<void>;
  loadOlderMessages: (chatId: string) => Promise<void>;
  setCurrentChat: (chatId: string | null) => void;
  clearPendingState: () => void;
  applyPausedState: (state: ResumePausedState) => void;
  loadPausedRun: (chatId: string) => Promise<void>;
  loadActiveRun: (chatId: string) => Promise<void>;
  abortStream: () => void;
  sendMessageStream: (
    chatId: string,
    message: string,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void,
    artifactIds?: string[],
    attachmentMeta?: unknown[]
  ) => Promise<boolean>;
  stopRun: (chatId: string, runId: string) => Promise<void>;
  resumeStream: (
    runId: string,
    action: 'confirm' | 'cancel' | 'input' | 'answer',
    input: string | boolean,
    onChunk: (chunk: string) => void,
    onError: (error: string) => void
  ) => Promise<boolean>;
}

const ChatActionsContext = createContext<ChatActions | null>(null);
const ChatMessagesStateContext = createContext<Pick<
  ChatState,
  | 'messagesByChat'
  | 'activeRun'
  | 'pendingConfirmations'
  | 'pendingInput'
  | 'pausedRunId'
  | 'hasInteraction'
  | 'isStreaming'
> | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messagesByChat, setMessagesByChat] = useState<
    Record<string, ChatHistory>
  >({});
  const [activeRun, setActiveRun] = useState<ActiveChatRun | null>(null);
  const [pendingConfirmations, setPendingConfirmations] = useState<
    PendingConfirmation[]
  >([]);
  const [pendingInput, setPendingInput] = useState<PendingInput | null>(null);
  const [pausedInteractionId, setPausedInteractionId] = useState<string | null>(
    null
  );
  const [hasInteraction, setHasInteraction] = useState(false);
  const [pausedRunId, setPausedRunId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const pauseLookupVersionRef = useRef(0);
  const historyVersionsRef = useRef<Record<string, number>>({});
  const historyRequestsRef = useRef<Record<string, number>>({});
  const invalidateHistory = useCallback((chatId: string) => {
    historyVersionsRef.current[chatId] =
      (historyVersionsRef.current[chatId] || 0) + 1;
  }, []);

  const loadMessages = useCallback(async (chatId: string) => {
    const streamVersion = historyVersionsRef.current[chatId] || 0;
    const requestVersion = (historyRequestsRef.current[chatId] || 0) + 1;
    historyRequestsRef.current[chatId] = requestVersion;
    setMessagesByChat(prev => ({
      ...prev,
      [chatId]: {
        ...prev[chatId],
        items: prev[chatId]?.items || [],
        loading: true,
        error: undefined,
      },
    }));
    try {
      const chatsApi = await import('@shared/api/chats');
      const resp = await chatsApi.listMessages(chatId, 100, undefined, { tail: true });
      if (historyRequestsRef.current[chatId] !== requestVersion) return;
      const items = (Array.isArray(resp?.items) ? resp.items : [])
        .map(item => toRenderableMessage(item))
        .filter((item): item is Message => item !== null);
      setMessagesByChat(prev => {
        // Restore older history while retaining messages received since this
        // request started. A later canonical reload replaces optimistic rows.
        const hasNewStream =
          (historyVersionsRef.current[chatId] || 0) !== streamVersion;
        const priorItems = (prev[chatId]?.items || []).filter(item => !item.isOptimistic);
        const merged = hasNewStream || priorItems.length
          ? [
              ...new Map(
                [...items, ...(hasNewStream ? (prev[chatId]?.items || []) : priorItems)].map(item => [
                  item.id,
                  item,
                ])
              ).values(),
            ]
          : items;
        return {
          ...prev,
          [chatId]: { items: merged, loading: false, loaded: true,
            olderCursor: prev[chatId]?.olderCursor || resp?.previous_cursor || undefined },
        };
      });
    } catch (err: unknown) {
      if (historyRequestsRef.current[chatId] !== requestVersion) return;
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: {
          ...prev[chatId],
          items: prev[chatId]?.items || [],
          loading: false,
          loaded: true,
          error:
            err instanceof Error ? err.message : 'Ошибка загрузки сообщений',
        },
      }));
    }
  }, []);

  const loadOlderMessages = useCallback(async (chatId: string) => {
    const cursor = messagesByChat[chatId]?.olderCursor;
    if (!cursor || messagesByChat[chatId]?.loading) return;
    setMessagesByChat(prev => ({ ...prev, [chatId]: { ...prev[chatId], loading: true } }));
    try {
      const chatsApi = await import('@shared/api/chats');
      const response = await chatsApi.listMessages(chatId, 100, undefined, { before: cursor });
      const older = (response.items || []).map(item => toRenderableMessage(item))
        .filter((item): item is Message => item !== null);
      setMessagesByChat(prev => ({
        ...prev,
        [chatId]: {
          ...prev[chatId],
          items: [...new Map([...older, ...(prev[chatId]?.items || [])].map(item => [item.id, item])).values()],
          olderCursor: response.previous_cursor || undefined,
          loading: false,
          loaded: true,
        },
      }));
    } catch (err: unknown) {
      setMessagesByChat(prev => ({ ...prev, [chatId]: { ...prev[chatId], loading: false,
        error: err instanceof Error ? err.message : 'Ошибка загрузки сообщений' } }));
    }
  }, [messagesByChat]);

  const clearPausedInteraction = useCallback(() => {
    pauseLookupVersionRef.current += 1;
    setPendingConfirmations([]);
    setPendingInput(null);
    setPausedRunId(null);
    setPausedInteractionId(null);
    setHasInteraction(false);
  }, []);

  const clearPendingState = useCallback(() => {
    clearPausedInteraction();
    setActiveRun(null);
  }, [clearPausedInteraction]);

  const applyPausedState = useCallback((resumeState: ResumePausedState) => {
    const reason = (resumeState.reason || '').trim() || 'paused';
    const question = (resumeState.question || '').trim();
    const message = (resumeState.message || '').trim();
    const runId = (resumeState.runId || '').trim();
    const action = resumeState.action || {};
    const actionQuestion =
      typeof action.question === 'string' ? action.question.trim() : '';
    const actionMessage =
      typeof action.message === 'string' ? action.message.trim() : '';
    const actionSummary =
      typeof action.summary === 'string' ? action.summary.trim() : '';
    const interactionQuestion =
      question || message || actionQuestion || actionMessage || actionSummary;

    // The public pause contract admits only explicit HITL states. Be
    // defensive for historical/buggy streams: a terminal failure must never
    // turn into a clarification form in the chat UI.
    if (reason !== 'waiting_input' && reason !== 'waiting_confirmation') {
      console.warn('Ignoring non-resumable chat pause state', reason);
      return;
    }

    // A just-arrived stream pause is newer than any in-flight restoration
    // lookup that may still be about to return an older empty response.
    pauseLookupVersionRef.current += 1;
    setHasInteraction(typeof resumeState.interaction?.id === 'string');
    setPausedRunId(runId || null);
    setPausedInteractionId(
      typeof action.pause_id === 'string' ? action.pause_id : null
    );

    if (reason === 'waiting_confirmation') {
      setPendingConfirmations([
        {
          operationFingerprint: String(action.operation_fingerprint || ''),
          toolSlug: String(action.tool_slug || ''),
          operation: String(action.operation || ''),
          riskLevel: String(action.risk_level || 'write'),
          argsPreview: String(action.args_preview || ''),
          question: interactionQuestion || 'Подтвердите действие',
          summary: actionSummary || message || actionMessage || '',
          runId: runId || null,
        },
      ]);
      setPendingInput(null);
      setActiveRun(current =>
        current
          ? {
              ...current,
              runId: runId || current.runId,
              status: 'waiting_confirmation',
            }
          : current
      );
      return;
    }

    setPendingConfirmations([]);
    setPendingInput({
      question: interactionQuestion || undefined,
      reason,
    });
    setActiveRun(current =>
      current
        ? { ...current, runId: runId || current.runId, status: 'waiting_input' }
        : current
    );
  }, []);

  const loadPausedRun = useCallback(
    async (chatId: string) => {
      const lookupVersion = ++pauseLookupVersionRef.current;
      try {
        const { getPausedRun } = await import('@shared/api/chats');
        const response = await getPausedRun(chatId);
        if (lookupVersion !== pauseLookupVersionRef.current) return;
        const pause: ChatPausedRun | null | undefined = response?.pause;
        if (!pause) {
          clearPausedInteraction();
          return;
        }
        applyPausedState({
          runId: pause.run_id,
          reason: pause.reason,
          question:
            typeof pause.context?.question === 'string'
              ? pause.context.question
              : undefined,
          message:
            typeof pause.context?.message === 'string'
              ? pause.context.message
              : undefined,
          action: pause.action,
          interaction:
            pause.context?.interaction &&
            typeof pause.context.interaction === 'object'
              ? (pause.context.interaction as Record<string, unknown>)
              : undefined,
        });
      } catch (err) {
        // A paused run is supplementary UI state. Message history remains usable
        // if it expires between the page load and this lookup.
        console.warn('Failed to restore paused chat run', err);
      }
    },
    [applyPausedState, clearPausedInteraction]
  );

  const {
    abortStream,
    setCurrentChat,
    sendMessageStream,
    resumeStream,
    attachRun,
    stopRun,
  } = useChatStreaming({
    activeRun,
    pausedInteractionId,
    hasInteraction,
    setActiveRun,
    setMessagesByChat,
    setIsStreaming,
    clearPendingState,
    clearPausedInteraction,
    applyPausedState,
    loadMessages,
    invalidateHistory,
  });

  const loadActiveRun = useCallback(
    async (chatId: string) => {
      try {
        await loadMessages(chatId);
        const { getActiveChatRun } = await import('@shared/api/chats');
        const { run } = await getActiveChatRun(chatId);
        if (run) {
          const activity = run.activity
            ? {
                runId: run.activity.run_id,
                stage: run.activity.stage,
                action: run.activity.action,
                description: run.activity.description,
                outcome: run.activity.outcome,
              }
            : undefined;
          const attached = await attachRun(chatId, run.run_id, run.user_message_id, activity);
          if (!attached) await loadMessages(chatId);
        }
      } catch (err) {
        console.warn('Failed to restore active chat run', err);
        await loadMessages(chatId);
      }
    },
    [attachRun, loadMessages]
  );

  const actionsValue = useMemo<ChatActions>(
    () => ({
      loadMessages,
      loadOlderMessages,
      setCurrentChat,
      clearPendingState,
      applyPausedState,
      loadPausedRun,
      loadActiveRun,
      abortStream,
      sendMessageStream,
      resumeStream,
      stopRun,
    }),
    [
      loadMessages,
      loadOlderMessages,
      setCurrentChat,
      clearPendingState,
      applyPausedState,
      loadPausedRun,
      loadActiveRun,
      abortStream,
      sendMessageStream,
      resumeStream,
      stopRun,
    ]
  );
  const messagesStateValue = useMemo(
    () => ({
      messagesByChat,
      activeRun,
      pendingConfirmations,
      pendingInput,
      pausedRunId,
      hasInteraction,
      isStreaming,
    }),
    [
      messagesByChat,
      activeRun,
      pendingConfirmations,
      pendingInput,
      pausedRunId,
      hasInteraction,
      isStreaming,
    ]
  );

  return (
    <ChatActionsContext.Provider value={actionsValue}>
      <ChatMessagesStateContext.Provider value={messagesStateValue}>
        {children}
      </ChatMessagesStateContext.Provider>
    </ChatActionsContext.Provider>
  );
}

export function useChatActions() {
  const context = useContext(ChatActionsContext);
  if (!context) {
    throw new Error('useChatActions must be used within ChatProvider');
  }
  return context;
}

export function useChatMessagesState() {
  const context = useContext(ChatMessagesStateContext);
  if (!context) {
    throw new Error('useChatMessagesState must be used within ChatProvider');
  }
  return context;
}

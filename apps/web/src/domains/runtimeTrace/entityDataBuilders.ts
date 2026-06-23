import type {
  AgentData,
  ErrorData,
  DialogData,
  DialogItem,
  InteractionData,
  LLMData,
  PublishedCollectionSnapshot,
  PublishedOperationSnapshot,
  PlannerData,
  RunData,
  SubAgentRun,
  ToolData,
  TraceEntity,
  UnknownData,
} from './entityTypes';
import type { SemanticEvent } from './types';

function parseJsonRecord(value: unknown): Record<string, unknown> | undefined {
  if (typeof value !== 'string') return undefined;
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return undefined;
    return parsed as Record<string, unknown>;
  } catch {
    return undefined;
  }
}

function inferLlmRole(
  purpose: string | undefined,
  parsedResponse: Record<string, unknown> | undefined,
  responseContent: string | undefined,
): { llmRole: NonNullable<LLMData['llmRole']>; llmRoleLabel: string } {
  const normalizedPurpose = String(purpose ?? '').trim().toLowerCase();
  const parsedFromContent = parseJsonRecord(responseContent);
  const selectedActionSummary = typeof parsedResponse?.selected_action_summary === 'string'
    ? parsedResponse.selected_action_summary
    : typeof parsedFromContent?.selected_action_summary === 'string'
      ? parsedFromContent.selected_action_summary
      : undefined;
  const hypotheses = parsedResponse?.hypotheses ?? parsedFromContent?.hypotheses;
  const parsedKind = String(parsedResponse?.kind ?? parsedFromContent?.kind ?? '').trim().toLowerCase();
  const trimmedContent = String(responseContent ?? '').trim();

  if (normalizedPurpose === 'planning_decision' && (Array.isArray(hypotheses) || selectedActionSummary)) {
    return { llmRole: 'reasoning', llmRoleLabel: 'Рассуждение' };
  }
  if (normalizedPurpose === 'planning_decision' || parsedKind === 'call_agent' || parsedKind === 'clarify' || parsedKind === 'final') {
    return { llmRole: 'planner_decision', llmRoleLabel: 'Следующий шаг' };
  }
  if (normalizedPurpose === 'tool_decision_or_answer' && trimmedContent.startsWith('```operation_call')) {
    return { llmRole: 'tool_protocol', llmRoleLabel: 'Протокол инструмента' };
  }
  if (normalizedPurpose === 'tool_decision_or_answer') {
    return { llmRole: 'agent_answer', llmRoleLabel: 'Ответ агента' };
  }
  if (normalizedPurpose === 'fact_extractor' || normalizedPurpose === 'summary_compactor') {
    return { llmRole: 'memory', llmRoleLabel: normalizedPurpose === 'fact_extractor' ? 'Извлечение фактов' : 'Сводка памяти' };
  }
  if (normalizedPurpose === 'final_answer') {
    return { llmRole: 'final_answer', llmRoleLabel: 'Финальный ответ' };
  }
  return { llmRole: 'generic', llmRoleLabel: 'LLM вызов' };
}

function inferErrorSource(raw: Record<string, unknown>): { source: NonNullable<ErrorData['source']>; sourceLabel: string } {
  const code = String(raw.error_code ?? '').trim().toLowerCase();
  const phase = String((raw._envelope as Record<string, unknown> | undefined)?.phase ?? '').trim().toLowerCase();
  if (code.startsWith('tool_') || code.includes('operation')) {
    return { source: 'tool', sourceLabel: 'Ошибка инструмента' };
  }
  if (code.startsWith('llm_')) {
    return { source: 'llm', sourceLabel: 'Ошибка LLM' };
  }
  if (code.startsWith('policy_') || code.includes('confirmation')) {
    return { source: 'policy', sourceLabel: 'Ошибка политики' };
  }
  if (phase === 'agent' || phase === 'planner' || code.startsWith('agent_') || code.startsWith('runtime_')) {
    return { source: 'runtime', sourceLabel: 'Ошибка рантайма' };
  }
  return { source: 'unknown', sourceLabel: 'Неизвестный источник' };
}

function normalizePublishedOperation(value: unknown): PublishedOperationSnapshot | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const operationSlug = record.operation_slug ?? record.operation ?? record.tool ?? record.name;
  if (typeof operationSlug !== 'string' || operationSlug.trim().length === 0) return null;
  return {
    operation_slug: operationSlug.trim(),
    canonical_name: typeof record.canonical_name === 'string' ? record.canonical_name : undefined,
    scope_kind: record.scope_kind === 'system' || record.scope_kind === 'collection' ? record.scope_kind : undefined,
    domain: typeof record.domain === 'string' ? record.domain : undefined,
    title: typeof record.title === 'string' ? record.title : undefined,
    description: typeof record.description === 'string' ? record.description : undefined,
    result_kind: typeof record.result_kind === 'string' ? record.result_kind : undefined,
    collection_slug: typeof record.collection_slug === 'string' ? record.collection_slug : undefined,
    collection_type: typeof record.collection_type === 'string' ? record.collection_type : undefined,
    collection_purpose: typeof record.collection_purpose === 'string' ? record.collection_purpose : undefined,
    collection_readiness: typeof record.collection_readiness === 'string' ? record.collection_readiness : undefined,
    schema_freshness: typeof record.schema_freshness === 'string' ? record.schema_freshness : undefined,
    provider_kind: typeof record.provider_kind === 'string' ? record.provider_kind : undefined,
    input_schema_summary: Array.isArray(record.input_schema_summary) ? record.input_schema_summary.map(String) : undefined,
    side_effects: typeof record.side_effects === 'boolean' ? record.side_effects : undefined,
    risk_level: record.risk_level === 'safe' || record.risk_level === 'write' || record.risk_level === 'destructive'
      ? record.risk_level
      : undefined,
  };
}

function normalizePublishedCollection(value: unknown): PublishedCollectionSnapshot | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (typeof record.collection_slug !== 'string' || record.collection_slug.trim().length === 0) return null;
  return {
    collection_slug: record.collection_slug.trim(),
    collection_type: typeof record.collection_type === 'string' ? record.collection_type : undefined,
    title: typeof record.title === 'string' ? record.title : undefined,
    purpose: typeof record.purpose === 'string' ? record.purpose : undefined,
    data_description: typeof record.data_description === 'string' ? record.data_description : undefined,
    readiness_status: typeof record.readiness_status === 'string' ? record.readiness_status : undefined,
    schema_freshness: typeof record.schema_freshness === 'string' ? record.schema_freshness : undefined,
    missing_requirements: Array.isArray(record.missing_requirements) ? record.missing_requirements.map(String) : undefined,
    available_operation_slugs: Array.isArray(record.available_operation_slugs) ? record.available_operation_slugs.map(String) : undefined,
  };
}

export function buildLLMData(events: SemanticEvent[]): LLMData {
  const request = events.find(e => e.raw_type === 'llm_request' || e.raw_type === 'llm_call' || e.raw_type === 'llm_turn');
  const response = events.find(e => e.raw_type === 'llm_response' || e.raw_type === 'llm_turn');
  const reqRaw = request?.raw?.raw ?? {};
  const reqInputs = request?.inputs ?? {};
  const respRaw = response?.raw?.raw ?? {};
  const respOutputs = response?.outputs ?? {};
  const toString = (value: unknown): string | undefined => (typeof value === 'string' ? value : undefined);
  const toNumber = (value: unknown): number | undefined => (typeof value === 'number' ? value : undefined);
  const toRecordArray = (value: unknown): Array<Record<string, unknown>> | undefined => (
    Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null) : undefined
  );
  const llmCallId = (reqRaw.llm_call_id ?? respRaw.llm_call_id) as string | undefined;
  const parentEntityType = (reqRaw.parent_entity_type ?? respRaw.parent_entity_type) as string | undefined;
  const parentEntityId = (reqRaw.parent_entity_id ?? respRaw.parent_entity_id) as string | undefined;
  const purpose = (reqRaw.purpose ?? respRaw.purpose) as string | undefined;
  const messages = toRecordArray(reqInputs.messages ?? reqRaw.messages ?? reqRaw.messages_sent);
  const systemPrompt = toString(reqInputs.systemPrompt ?? reqInputs.system_prompt ?? reqRaw.system_prompt ?? reqRaw.compiled_prompt ?? reqRaw.prompt);
  const isBriefMode = !!(respRaw.messages_hash || respRaw.system_prompt_hash);
  const messagesHash = typeof respRaw.messages_hash === 'string' ? respRaw.messages_hash : undefined;
  const systemPromptHash = typeof respRaw.system_prompt_hash === 'string' ? respRaw.system_prompt_hash : undefined;
  const responseContent = (respOutputs.content ?? respOutputs.response ?? respOutputs.text ?? respRaw.content ?? respRaw.response ?? respRaw.text) as string | undefined;
  const rawResponse = (respRaw.content ?? respRaw.response ?? respRaw.text ?? respOutputs.content ?? respOutputs.response ?? respOutputs.text) as string | undefined;
  const parsedResponse = (respOutputs.parsed_response ?? respOutputs.parsedResponse ?? respRaw.parsed_response ?? respRaw.parsedResponse) as Record<string, unknown> | undefined;
  const roleMeta = inferLlmRole(typeof purpose === 'string' ? purpose : undefined, parsedResponse, responseContent ?? rawResponse);
  const toolCalls: Array<{ tool: string; arguments: Record<string, unknown>; callId?: string }> = [];
  if (parsedResponse?.tool_calls && Array.isArray(parsedResponse.tool_calls)) {
    for (const tc of parsedResponse.tool_calls) {
      if (typeof tc === 'object' && tc !== null) {
        toolCalls.push({
          tool: String(tc.tool ?? tc.name ?? tc.function?.name ?? 'unknown'),
          arguments: (tc.arguments ?? tc.function?.arguments ?? tc.params ?? {}) as Record<string, unknown>,
          callId: (tc.call_id ?? tc.id) as string | undefined,
        });
      }
    }
  }
  const tokensInRaw = respRaw.tokens_in ?? respOutputs.tokens_in;
  const tokensOutRaw = respRaw.tokens_out ?? respOutputs.tokens_out;
  const tokensTotalRaw = respRaw.tokens_total ?? respOutputs.tokens_total;
  const tokensIn = toNumber(tokensInRaw);
  const tokensOut = toNumber(tokensOutRaw);
  const tokensTotal = toNumber(tokensTotalRaw) ?? (
    tokensIn !== undefined || tokensOut !== undefined
      ? Number(tokensIn ?? 0) + Number(tokensOut ?? 0)
      : undefined
  );
  return {
    kind: 'llm',
    llmCallId: typeof llmCallId === 'string' ? llmCallId : undefined,
    parentEntityType: typeof parentEntityType === 'string' ? parentEntityType : undefined,
    parentEntityId: typeof parentEntityId === 'string' ? parentEntityId : undefined,
    purpose: typeof purpose === 'string' ? purpose : undefined,
    llmRole: roleMeta.llmRole,
    llmRoleLabel: roleMeta.llmRoleLabel,
    prompt: messages || systemPrompt || messagesHash || systemPromptHash ? { messages, systemPrompt, isBriefMode, messagesHash, systemPromptHash } : undefined,
    response: responseContent || rawResponse ? {
      content: responseContent,
      rawResponse,
      responseLength: typeof respOutputs.responseLength === 'number' ? respOutputs.responseLength : (responseContent?.length ?? rawResponse?.length),
    } : undefined,
    decision: toolCalls.length > 0 ? { toolCalls } : undefined,
    params: {
      model: toString(reqInputs.model ?? reqRaw.model),
      temperature: toNumber(reqInputs.temperature ?? reqRaw.temperature),
      maxTokens: toNumber(reqInputs.maxTokens ?? reqInputs.max_tokens ?? reqRaw.max_tokens),
    },
    tokensIn,
    tokensOut,
    tokensTotal,
  };
}

export function buildToolData(events: SemanticEvent[]): ToolData {
  const call = events.find(e => e.raw_type === 'operation_call' || e.raw_type === 'tool_call');
  const result = events.find(e => e.raw_type === 'operation_result' || e.raw_type === 'tool_result');
  const retries = events.filter(e => e.raw_type === 'protocol_retry');
  const rawCall = call?.raw?.raw ?? {};
  const callInputs = call?.inputs ?? {};
  const rawResult = result?.raw?.raw ?? {};
  const resultOutputs = result?.outputs ?? {};
  const toolSlug = String(callInputs.operation_slug ?? callInputs.tool ?? callInputs.operation ?? rawCall.operation_slug ?? rawCall.tool ?? rawCall.operation ?? 'unknown');
  const callId = String(callInputs.call_id ?? rawCall.call_id ?? '');
  const llmCallId = (callInputs.llm_call_id ?? rawCall.llm_call_id ?? resultOutputs.llm_call_id ?? rawResult.llm_call_id) as string | undefined;
  const calledByAgentSlug = (callInputs.agent_slug ?? rawCall.agent_slug ?? resultOutputs.agent_slug ?? rawResult.agent_slug) as string | undefined;
  const calledByAgentRunId = (callInputs.agent_run_id ?? rawCall.agent_run_id ?? resultOutputs.agent_run_id ?? rawResult.agent_run_id) as string | undefined;
  const args = (callInputs.arguments ?? callInputs.parameters ?? callInputs.input ?? callInputs.payload ?? rawCall.arguments ?? rawCall.parameters ?? rawCall.input ?? rawCall.payload ?? {}) as Record<string, unknown>;
  const successRaw = (resultOutputs.success ?? rawResult.success);
  const success = successRaw === true;
  const resultData = success ? (resultOutputs.result ?? resultOutputs.output ?? resultOutputs.data ?? rawResult.result ?? rawResult.output ?? rawResult.data) : undefined;
  const fallbackFailure = resultOutputs.result ?? resultOutputs.output ?? resultOutputs.data ?? rawResult.result ?? rawResult.output ?? rawResult.data;
  const envelope = (
    (rawResult.result_envelope && typeof rawResult.result_envelope === 'object' ? rawResult.result_envelope : undefined)
    ?? (rawResult.result && typeof rawResult.result === 'object' ? rawResult.result : undefined)
  ) as Record<string, unknown> | undefined;
  const errorMessage = !success
    ? String(
        resultOutputs.error
        ?? resultOutputs.safe_message
        ?? resultOutputs.message
        ?? rawResult.error
        ?? rawResult.safe_message
        ?? rawResult.message
        ?? (typeof envelope?.safe_message === 'string' ? envelope.safe_message : undefined)
        ?? (typeof fallbackFailure === 'string' ? fallbackFailure : undefined)
        ?? (typeof (fallbackFailure as Record<string, unknown> | undefined)?.error === 'string'
          ? (fallbackFailure as Record<string, unknown>).error
          : undefined)
        ?? 'Failed'
      )
    : undefined;
  const operatorMessage = !success
    ? (
        typeof rawResult.error === 'string' ? rawResult.error
        : typeof rawResult.message === 'string' ? rawResult.message
        : typeof fallbackFailure === 'string' ? fallbackFailure
        : undefined
      )
    : undefined;
  const errorCodeRaw = resultOutputs.error_code ?? rawResult.error_code;
  const retryableRaw = resultOutputs.retryable ?? rawResult.retryable;
  return {
    kind: 'tool',
    toolSlug,
    callId: callId || undefined,
    llmCallId: typeof llmCallId === 'string' ? llmCallId : undefined,
    calledByAgentSlug: typeof calledByAgentSlug === 'string' ? calledByAgentSlug : undefined,
    calledByAgentRunId: typeof calledByAgentRunId === 'string' ? calledByAgentRunId : undefined,
    arguments: Object.keys(args).length > 0 ? args : undefined,
    result: {
      success,
      data: resultData,
      error: errorMessage,
      safeMessage: errorMessage,
      operatorMessage,
      errorCode: typeof errorCodeRaw === 'string' ? errorCodeRaw : undefined,
      retryable: typeof retryableRaw === 'boolean' ? retryableRaw : undefined,
      envelope,
    },
    retries: retries.length > 0 ? retries.map((r, i) => ({
      attempt: i + 1,
      error: String(r.decision?.reason ?? r.summary ?? r.outputs?.error ?? r.raw?.raw?.error ?? ''),
    })) : undefined,
  };
}

export function buildPlannerData(event: SemanticEvent): PlannerData {
  const raw = event.raw?.raw ?? {};
  const decision = event.decision ?? {};
  const inputs = event.inputs ?? {};
  const kind = String(raw.kind ?? raw.action_type ?? raw.action ?? decision.kind ?? decision.action_type ?? decision.action ?? 'planner_decision');
  const rationale = typeof raw.rationale === 'string' ? raw.rationale : typeof decision.rationale === 'string' ? decision.rationale : typeof event.summary === 'string' ? event.summary : undefined;
  const availableAgents = raw.available_agents ?? raw.availableAgents ?? decision.available_agents ?? decision.availableAgents ?? inputs.available_agents ?? inputs.availableAgents;
  const previousResults = raw.previous_results ?? raw.previousResults ?? raw.facts ?? decision.previous_results ?? decision.previousResults ?? decision.facts ?? inputs.previous_results ?? inputs.previousResults;
  const goal = typeof raw.goal === 'string' ? raw.goal : typeof inputs.goal === 'string' ? inputs.goal : typeof decision.goal === 'string' ? decision.goal : undefined;
  const alternatives = (raw.alternatives ?? decision.alternatives) as PlannerData['alternatives'] ?? undefined;
  const agentSlug = raw.agent_slug ?? raw.agent ?? decision.agent_slug ?? decision.agent ?? decision.chosenAgentSlug ?? '';
  const agentInput = raw.agent_input ?? decision.agent_input ?? decision.agentInput ?? decision.chosenAgentInput ?? undefined;
  const hypothesesRaw = raw.hypotheses ?? decision.hypotheses;
  const hypotheses = Array.isArray(hypothesesRaw)
    ? hypothesesRaw
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map((item) => ({
          summary: String(item.summary ?? ''),
          rationale: typeof item.rationale === 'string' ? item.rationale : undefined,
          risks: Array.isArray(item.risks) ? item.risks.map(String) : undefined,
          expectedOutcome: typeof item.expected_outcome === 'string' ? item.expected_outcome : undefined,
        }))
    : undefined;
  return {
    kind: 'planner',
    stepKind: kind,
    rationale,
    thinking: kind === 'thinking' ? {
      executionMode: typeof raw.execution_mode === 'string' ? raw.execution_mode : undefined,
      hypotheses,
      selectedHypothesisIndex: typeof raw.selected_hypothesis_index === 'number' ? raw.selected_hypothesis_index : undefined,
      selectedActionKind: typeof raw.selected_action_kind === 'string' ? raw.selected_action_kind : undefined,
      selectedActionSummary: typeof raw.selected_action_summary === 'string' ? raw.selected_action_summary : undefined,
      selectionRationale: typeof raw.selection_rationale === 'string' ? raw.selection_rationale : undefined,
    } : undefined,
    alternatives,
    inputs: {
      goal,
      availableAgents: Array.isArray(availableAgents) ? availableAgents.map(String) : undefined,
      previousResults: Array.isArray(previousResults) ? previousResults : undefined,
    },
    decision: kind === 'call_agent' || kind.includes('agent') ? {
      chosenAgentSlug: String(agentSlug),
      agentInput: agentInput as Record<string, unknown> ?? undefined,
    } : undefined,
  };
}

export function buildAgentData(events: SemanticEvent[], subAgentRun?: SubAgentRun): AgentData {
  const firstPlannerStep = events.find(e =>
    e.raw_type === 'planner_decision' &&
    (e.raw?.raw?.kind === 'call_agent' || e.decision?.kind === 'call_agent')
  );
  const rawPlanner = firstPlannerStep?.raw?.raw ?? {};
  const slug = String(rawPlanner.agent_slug ?? rawPlanner.agent ?? 'unknown');
  const partialModeEvent = events.find(e => e.raw_type === 'partial_mode' || e.raw?.raw?.partial_mode_warning);
  const partialModeWarning = partialModeEvent
    ? String(partialModeEvent.raw?.raw?.warning ?? partialModeEvent.raw?.raw?.partial_mode_warning ?? '')
    : undefined;
  const userRequest = events.find(e => e.raw_type === 'user_request');
  const hasOverrides = !!userRequest?.raw?.raw?.has_overrides;
  const contextSnapshot = userRequest?.raw?.raw?.context_snapshot as Record<string, unknown> | undefined;
  const snapshotMeta = contextSnapshot?.meta && typeof contextSnapshot.meta === 'object'
    ? contextSnapshot.meta as Record<string, unknown>
    : undefined;
  const availableOperationsRaw = Array.isArray(snapshotMeta?.available_operations)
    ? snapshotMeta.available_operations
    : Array.isArray(contextSnapshot?.available_operations)
      ? contextSnapshot.available_operations
      : [];
  const availableOperations = availableOperationsRaw
    .map(normalizePublishedOperation)
    .filter((item): item is PublishedOperationSnapshot => item !== null);
  const availableCollectionsRaw = Array.isArray(snapshotMeta?.available_collections)
    ? snapshotMeta.available_collections
    : Array.isArray(contextSnapshot?.available_collections)
      ? contextSnapshot.available_collections
      : [];
  const availableCollections = availableCollectionsRaw
    .map(normalizePublishedCollection)
    .filter((item): item is PublishedCollectionSnapshot => item !== null);
  const toolsAvailable = availableOperations.length > 0
    ? availableOperations.map(op => op.operation_slug)
    : undefined;
  return {
    kind: 'agent',
    slug,
    versionId: subAgentRun ? String(subAgentRun.runId) : undefined,
    versionLabel: subAgentRun ? 'sub-agent' : undefined,
    hasOverrides,
    toolsAvailable,
    availableOperations: availableOperations.length > 0 ? availableOperations : undefined,
    availableCollections: availableCollections.length > 0 ? availableCollections : undefined,
    partialModeWarning,
  };
}

export function buildInteractionData(event: SemanticEvent): InteractionData {
  const raw = event.raw?.raw ?? {};
  const resumeAction = typeof raw.resume_action === 'string' ? raw.resume_action : undefined;
  const questionKind = typeof raw.question_kind === 'string' ? raw.question_kind : undefined;
  const interactionKind = typeof raw.interaction_kind === 'string' ? raw.interaction_kind : undefined;
  const fallbackKind = event.raw_type === 'confirmation_required'
    ? 'confirm'
    : event.raw_type === 'waiting_input' || event.raw_type === 'question_answer'
      ? 'clarify'
      : 'resume';
  const answerText = typeof raw.user_answer === 'string' ? raw.user_answer
    : typeof raw.answer === 'string' ? raw.answer
    : undefined;
  return {
    kind: 'interaction',
    interactionKind: interactionKind ?? questionKind ?? resumeAction ?? fallbackKind,
    question: typeof raw.question === 'string'
      ? raw.question
      : typeof raw.message === 'string'
        ? raw.message
        : undefined,
    answer: answerText,
    resumeAction,
    sourceRunId: typeof raw.source_run_id === 'string' ? raw.source_run_id : undefined,
  };
}

export function buildDialogData(
  interactionKind: DialogData['interactionKind'],
  items: DialogItem[],
): DialogData {
  const primary = items[0];
  return {
    kind: 'dialog',
    interactionKind,
    question: primary?.question,
    answer: primary?.answer,
    items: items.length > 0 ? items : undefined,
  };
}

export function buildErrorData(event: SemanticEvent): ErrorData {
  const raw = event.raw?.raw ?? {};
  const sourceMeta = inferErrorSource(raw);
  return {
    kind: 'error',
    code: typeof raw.error_code === 'string' ? raw.error_code : undefined,
    userMessage: String(raw.user_message ?? raw.message ?? raw.error ?? 'Unknown error'),
    operatorMessage: typeof raw.operator_message === 'string' ? raw.operator_message : undefined,
    source: sourceMeta.source,
    sourceLabel: sourceMeta.sourceLabel,
    debug: raw.debug as ErrorData['debug'] ?? undefined,
  };
}

export function buildUnknownData(event: SemanticEvent): UnknownData {
  return {
    kind: 'unknown',
    rawType: event.raw_type,
    raw: event.raw?.raw ?? {},
    hint: `Тип "${event.raw_type}" не классифицирован — добавь в normalize.ts и buildEntityTree.ts`,
  };
}

export function buildRunData(events: SemanticEvent[]): RunData {
  const userRequest = events.find(e => e.raw_type === 'user_request');
  const finalResponse = events.find(e => e.raw_type === 'final_response' || e.raw_type === 'final');
  const error = events.find(e => e.raw_type === 'error' && e.status === 'error');
  const routingDecisions = events
    .filter(e => e.raw_type === 'routing_decision' || e.raw_type === 'routing')
    .map(e => ({
      agentSlug: typeof e.decision?.agent_slug === 'string' ? e.decision.agent_slug : undefined,
      reason: String(e.summary ?? e.decision?.reason ?? ''),
      timestamp: e.started_at,
    }));
  return {
    kind: 'run',
    userRequest: typeof userRequest?.inputs?.content === 'string' ? userRequest.inputs.content : String(userRequest?.summary ?? ''),
    agentSlug: typeof userRequest?.raw?.raw?.agent_slug === 'string' ? userRequest.raw.raw.agent_slug : undefined,
    finalContent: finalResponse?.outputs?.content as string | undefined,
    finalError: error?.status === 'error' ? String(error.summary) : undefined,
    routingDecisions: routingDecisions.length > 0 ? routingDecisions : undefined,
  };
}

export function enrichPlannerIterationFromStepData(container: TraceEntity, plannerData: PlannerData): void {
  if (container.data.kind !== 'planner') return;
  container.data.stepKind = plannerData.stepKind;
  if (plannerData.rationale) container.data.rationale = plannerData.rationale;
  if (plannerData.decision) container.data.decision = plannerData.decision;
  const label = String((container.data as PlannerData).stepKind ?? 'iteration');
  container.title = `Step: ${label}`;
}

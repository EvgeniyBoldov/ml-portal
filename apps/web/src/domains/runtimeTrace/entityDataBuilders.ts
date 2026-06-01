import type {
  AgentData,
  ErrorData,
  LLMData,
  PlannerData,
  RunData,
  SubAgentRun,
  ToolData,
  TraceEntity,
  UnknownData,
} from './entityTypes';
import type { SemanticEvent } from './types';

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
  const errorMessage = !success
    ? String(
        resultOutputs.error
        ?? resultOutputs.message
        ?? rawResult.error
        ?? rawResult.message
        ?? (typeof fallbackFailure === 'string' ? fallbackFailure : undefined)
        ?? (typeof (fallbackFailure as Record<string, unknown> | undefined)?.error === 'string'
          ? (fallbackFailure as Record<string, unknown>).error
          : undefined)
        ?? 'Failed'
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
      errorCode: typeof errorCodeRaw === 'string' ? errorCodeRaw : undefined,
      retryable: typeof retryableRaw === 'boolean' ? retryableRaw : undefined,
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
  return {
    kind: 'planner',
    stepKind: kind,
    rationale,
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
  const toolsAvailable = Array.isArray(contextSnapshot?.available_operations)
    ? contextSnapshot.available_operations.map(op => typeof op === 'string' ? op : String(op.operation_slug ?? op.tool ?? op))
    : undefined;
  return {
    kind: 'agent',
    slug,
    versionId: subAgentRun ? String(subAgentRun.runId) : undefined,
    versionLabel: subAgentRun ? 'sub-agent' : undefined,
    hasOverrides,
    toolsAvailable,
    partialModeWarning,
  };
}

export function buildErrorData(event: SemanticEvent): ErrorData {
  const raw = event.raw?.raw ?? {};
  return {
    kind: 'error',
    code: typeof raw.error_code === 'string' ? raw.error_code : undefined,
    userMessage: String(raw.user_message ?? raw.message ?? raw.error ?? 'Unknown error'),
    operatorMessage: typeof raw.operator_message === 'string' ? raw.operator_message : undefined,
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
  container.title = `Plan: ${label}`;
}

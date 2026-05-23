import { useMemo, useState } from 'react';

import type { ExecutionLimitsUpdate, Model, ResponseContract, SystemLLMRole, SystemLLMRoleUpdate } from '@/shared/api/admin';
import { useModels } from '@/shared/api/hooks/useAdmin';
import {
  useActiveFactExtractorRole,
  useActivePlannerRole,
  useActiveSummaryCompactorRole,
  useActiveSynthesizerRole,
  useOrchestratorExecutionLimits,
  useUpdateFactExtractorRole,
  useUpdateOrchestratorExecutionLimits,
  useUpdatePlannerRole,
  useUpdateSummaryCompactorRole,
  useUpdateSynthesizerRole,
} from '@/shared/api/hooks/usePlatformSettings';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, EntityPageV2, Tab } from '@/shared/ui';
import type { GridFieldConfig as FieldConfig } from '@/shared/ui';
import { ContractAwareEditor } from '@/shared/ui/ContractAwareEditor';
import {
  FACT_EXTRACTOR_INPUT_CONTRACT,
  PLANNER_INPUT_CONTRACT,
  SUMMARY_COMPACTOR_INPUT_CONTRACT,
  SYNTHESIZER_INPUT_CONTRACT,
} from '@/shared/constants/orchestratorContracts';

const ROLE_PARAM_KEYS = ['model', 'temperature'];

type RoleFormData = SystemLLMRoleUpdate & Record<string, unknown>;

const DEFAULT_ROLE_FORM: RoleFormData = {
  identity: '',
  mission: '',
  rules: '',
  safety: '',
  output_requirements: '',
  model: '',
  temperature: 0.2,
};

const LLM_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'llm_input_tokens_max', type: 'number', label: 'LLM input токены', description: 'Лимит токенов входного промпта для одного LLM-вызова.' },
  { key: 'llm_output_tokens_max', type: 'number', label: 'LLM output токены', description: 'Лимит токенов ответа для одного LLM-вызова.' },
  { key: 'llm_context_window_max', type: 'number', label: 'LLM context window', description: 'Лимит input+output токенов в одном LLM-вызове.' },
];

const RUNTIME_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'runtime_steps_max', type: 'number', label: 'Runtime шаги', description: 'Лимит шагов рантайма роли.' },
  { key: 'runtime_tool_calls_max', type: 'number', label: 'Runtime вызовы инструментов', description: 'Лимит числа tool-вызовов за ран.' },
  { key: 'runtime_retries_max', type: 'number', label: 'Runtime ретраи', description: 'Лимит повторных попыток.' },
  { key: 'runtime_wall_time_ms_max', type: 'number', label: 'Runtime wall time (ms)', description: 'Лимит общего времени выполнения в мс.' },
  { key: 'runtime_tokens_total_max', type: 'number', label: 'Runtime total токены', description: 'Лимит суммарных токенов рантайма.' },
];

const roleFields = (
  modelOptions: Array<{ value: string; label: string }>,
  labels: { identity: string; mission: string; rules: string; safety: string; outputRequirements: string; model: string },
  outputContract: ResponseContract | null,
  inputContract: Record<string, unknown> | null,
): FieldConfig[] => [
  { key: 'identity', label: 'Идентичность', type: 'textarea', rows: 4, description: labels.identity },
  { key: 'mission', label: 'Миссия', type: 'textarea', rows: 6, description: labels.mission },
  {
    key: 'rules',
    label: 'Правила',
    type: 'custom',
    description: labels.rules,
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={(next) => onChange(next)}
        outputContract={outputContract}
        inputContract={inputContract}
        fieldLabel="Правила"
        disabled={!editable}
        rows={10}
        placeholder="Опиши, как должна себя вести роль..."
      />
    ),
  },
  {
    key: 'safety',
    label: 'Безопасность',
    type: 'custom',
    description: labels.safety,
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={(next) => onChange(next)}
        outputContract={outputContract}
        inputContract={inputContract}
        fieldLabel="Безопасность"
        disabled={!editable}
        rows={6}
        placeholder="Опиши ограничения и запреты..."
      />
    ),
  },
  {
    key: 'output_requirements',
    label: 'Критерии ответа',
    type: 'custom',
    description: labels.outputRequirements,
    render: (value, editable, onChange) => (
      <ContractAwareEditor
        value={String(value ?? '')}
        onChange={(next) => onChange(next)}
        outputContract={outputContract}
        inputContract={inputContract}
        fieldLabel="Критерии ответа"
        disabled={!editable}
        rows={8}
        placeholder="Опиши, каким должен быть ответ и какие критерии он должен соблюдать..."
      />
    ),
  },
  { key: 'model', label: 'Модель', type: 'select', options: modelOptions, description: labels.model },
  { key: 'temperature', label: 'Temperature', type: 'number' },
];

function mapRoleToFields(role?: SystemLLMRole): RoleFormData {
  return {
    identity: role?.identity ?? DEFAULT_ROLE_FORM.identity,
    mission: role?.mission ?? DEFAULT_ROLE_FORM.mission,
    rules: role?.rules ?? DEFAULT_ROLE_FORM.rules,
    safety: role?.safety ?? DEFAULT_ROLE_FORM.safety,
    output_requirements: role?.output_requirements ?? DEFAULT_ROLE_FORM.output_requirements,
    model: role?.model ?? DEFAULT_ROLE_FORM.model,
    temperature: role?.temperature ?? DEFAULT_ROLE_FORM.temperature,
  };
}

function canEditOutputRequirements(contract: ResponseContract | null | undefined): boolean {
  return !contract || contract.format !== 'json';
}

export function OrchestrationPage() {
  const [plannerMode, setPlannerMode] = useState<'view' | 'edit'>('view');
  const [plannerForm, setPlannerForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [plannerLimitsForm, setPlannerLimitsForm] = useState<Record<string, unknown>>({});

  const [synthMode, setSynthMode] = useState<'view' | 'edit'>('view');
  const [synthForm, setSynthForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [synthLimitsForm, setSynthLimitsForm] = useState<Record<string, unknown>>({});

  const [factMode, setFactMode] = useState<'view' | 'edit'>('view');
  const [factForm, setFactForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [factLimitsForm, setFactLimitsForm] = useState<Record<string, unknown>>({});

  const [compactMode, setCompactMode] = useState<'view' | 'edit'>('view');
  const [compactForm, setCompactForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [compactLimitsForm, setCompactLimitsForm] = useState<Record<string, unknown>>({});

  const { data: plannerRole, isLoading: plannerLoading } = useActivePlannerRole();
  const { data: synthesizerRole, isLoading: synthesizerLoading } = useActiveSynthesizerRole();
  const { data: factExtractorRole, isLoading: factExtractorLoading } = useActiveFactExtractorRole();
  const { data: summaryCompactorRole, isLoading: summaryCompactorLoading } = useActiveSummaryCompactorRole();

  const { data: plannerLimits, isLoading: plannerLimitsLoading } = useOrchestratorExecutionLimits('planner');
  const { data: synthLimits, isLoading: synthLimitsLoading } = useOrchestratorExecutionLimits('synthesizer');
  const { data: factLimits, isLoading: factLimitsLoading } = useOrchestratorExecutionLimits('fact_extractor');
  const { data: compactLimits, isLoading: compactLimitsLoading } = useOrchestratorExecutionLimits('summary_compactor');

  const updatePlannerRole = useUpdatePlannerRole();
  const updateSynthesizerRole = useUpdateSynthesizerRole();
  const updateFactExtractorRole = useUpdateFactExtractorRole();
  const updateSummaryCompactorRole = useUpdateSummaryCompactorRole();

  const updatePlannerLimits = useUpdateOrchestratorExecutionLimits('planner');
  const updateSynthLimits = useUpdateOrchestratorExecutionLimits('synthesizer');
  const updateFactLimits = useUpdateOrchestratorExecutionLimits('fact_extractor');
  const updateCompactLimits = useUpdateOrchestratorExecutionLimits('summary_compactor');

  const { data: modelsData, isLoading: modelsLoading } = useModels({ type: 'llm_chat', enabled_only: true });

  const modelOptions = useMemo(
    () => (modelsData?.items ?? []).map((model: Model) => ({ value: model.alias, label: `${model.name} (${model.alias})` })),
    [modelsData]
  );

  const resolvedPlannerFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль planner-агента в процессе выполнения.',
    mission: 'Главная цель планировщика на каждом шаге.',
    rules: 'Логика переходов между фазами и выбора действий. Описывает семантику полей контракта.',
    safety: 'Ограничения и контроль риска для планирования.',
    outputRequirements: 'Что именно должен вернуть planner по итогам шага и в каком виде.',
    model: 'LLM-модель planner.',
  }, plannerRole?.response_contract ?? null, PLANNER_INPUT_CONTRACT), [modelOptions, plannerRole?.response_contract]);
  const resolvedSynthesizerFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль синтезатора итогового ответа.',
    mission: 'Сборка финального ответа пользователя из фактов рантайма.',
    rules: 'Правила формирования ответа и опоры на факты. Контракт определяет формат (plain_text).',
    safety: 'Ограничения на чувствительные данные в финальном ответе.',
    outputRequirements: 'Требования к финальному тексту и критериям качества ответа.',
    model: 'LLM-модель synthesizer.',
  }, synthesizerRole?.response_contract ?? null, SYNTHESIZER_INPUT_CONTRACT), [modelOptions, synthesizerRole?.response_contract]);
  const resolvedFactExtractorFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль экстрактора фактов.',
    mission: 'Извлечение атомарных фактов из диалога.',
    rules: 'Правила отбора и нормализации фактов. Описывает структуру facts[].',
    safety: 'Что запрещено сохранять в фактах.',
    outputRequirements: 'Требования к структуре и качеству извлекаемых фактов.',
    model: 'LLM-модель fact extractor.',
  }, factExtractorRole?.response_contract ?? null, FACT_EXTRACTOR_INPUT_CONTRACT), [modelOptions, factExtractorRole?.response_contract]);
  const resolvedSummaryCompactorFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль компактора rolling summary.',
    mission: 'Обновление структурного summary диалога.',
    rules: 'Правила обновления goals/done/entities/open_questions. Описывает семантику полей.',
    safety: 'Ограничения на чувствительные данные в summary.',
    outputRequirements: 'Требования к обновлению summary и структуре итогового среза.',
    model: 'LLM-модель summary compactor.',
  }, summaryCompactorRole?.response_contract ?? null, SUMMARY_COMPACTOR_INPUT_CONTRACT), [modelOptions, summaryCompactorRole?.response_contract]);

  const toLimitsUpdate = (form: Record<string, unknown>): ExecutionLimitsUpdate => ({
    llm_input_tokens_max: form.llm_input_tokens_max as number | null | undefined,
    llm_output_tokens_max: form.llm_output_tokens_max as number | null | undefined,
    llm_context_window_max: form.llm_context_window_max as number | null | undefined,
    runtime_steps_max: form.runtime_steps_max as number | null | undefined,
    runtime_tool_calls_max: form.runtime_tool_calls_max as number | null | undefined,
    runtime_retries_max: form.runtime_retries_max as number | null | undefined,
    runtime_wall_time_ms_max: form.runtime_wall_time_ms_max as number | null | undefined,
    runtime_tokens_total_max: form.runtime_tokens_total_max as number | null | undefined,
  });

  return (
    <>
      <EntityPageV2
        title="Оркестрация"
        mode="view"
        breadcrumbs={[
          { label: 'Администрирование', href: '/admin' },
          { label: 'Оркестрация', href: '/admin/orchestration' },
        ]}
      >
        <Tab
          title="Planner"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: plannerMode,
            saving: updatePlannerRole.isPending || updatePlannerLimits.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => {
              setPlannerForm(mapRoleToFields(plannerRole));
              setPlannerLimitsForm({ ...(plannerLimits || {}) });
              setPlannerMode('edit');
            },
            onSave: async () => {
              await Promise.all([
                updatePlannerRole.mutateAsync(plannerForm),
                updatePlannerLimits.mutateAsync(toLimitsUpdate(plannerLimitsForm)),
              ]);
              setPlannerMode('view');
            },
            onCancel: () => { setPlannerMode('view'); setPlannerForm(DEFAULT_ROLE_FORM); setPlannerLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedPlannerFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedPlannerFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
          {canEditOutputRequirements(plannerRole?.response_contract) ? (
            <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedPlannerFields.filter((f) => f.key === 'output_requirements')} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
          ) : null}
          <Block title="Лимиты LLM" icon="zap" iconVariant="warning" width="1/2" fields={LLM_LIMIT_FIELDS} data={plannerMode === 'edit' ? plannerLimitsForm : (plannerLimits || {})} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Лимиты Runtime" icon="settings" iconVariant="info" width="1/2" fields={RUNTIME_LIMIT_FIELDS} data={plannerMode === 'edit' ? plannerLimitsForm : (plannerLimits || {})} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Synthesizer"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: synthMode,
            saving: updateSynthesizerRole.isPending || updateSynthLimits.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setSynthForm(mapRoleToFields(synthesizerRole)); setSynthLimitsForm({ ...(synthLimits || {}) }); setSynthMode('edit'); },
            onSave: async () => {
              await Promise.all([
                updateSynthesizerRole.mutateAsync(synthForm),
                updateSynthLimits.mutateAsync(toLimitsUpdate(synthLimitsForm)),
              ]);
              setSynthMode('view');
            },
            onCancel: () => { setSynthMode('view'); setSynthForm(DEFAULT_ROLE_FORM); setSynthLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedSynthesizerFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedSynthesizerFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
          {canEditOutputRequirements(synthesizerRole?.response_contract) ? (
            <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedSynthesizerFields.filter((f) => f.key === 'output_requirements')} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
          ) : null}
          <Block title="Лимиты LLM" icon="zap" iconVariant="warning" width="1/2" fields={LLM_LIMIT_FIELDS} data={synthMode === 'edit' ? synthLimitsForm : (synthLimits || {})} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Лимиты Runtime" icon="settings" iconVariant="info" width="1/2" fields={RUNTIME_LIMIT_FIELDS} data={synthMode === 'edit' ? synthLimitsForm : (synthLimits || {})} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Fact Extractor"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: factMode,
            saving: updateFactExtractorRole.isPending || updateFactLimits.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setFactForm(mapRoleToFields(factExtractorRole)); setFactLimitsForm({ ...(factLimits || {}) }); setFactMode('edit'); },
            onSave: async () => {
              await Promise.all([
                updateFactExtractorRole.mutateAsync(factForm),
                updateFactLimits.mutateAsync(toLimitsUpdate(factLimitsForm)),
              ]);
              setFactMode('view');
            },
            onCancel: () => { setFactMode('view'); setFactForm(DEFAULT_ROLE_FORM); setFactLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedFactExtractorFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedFactExtractorFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
          {canEditOutputRequirements(factExtractorRole?.response_contract) ? (
            <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedFactExtractorFields.filter((f) => f.key === 'output_requirements')} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
          ) : null}
          <Block title="Лимиты LLM" icon="zap" iconVariant="warning" width="1/2" fields={LLM_LIMIT_FIELDS} data={factMode === 'edit' ? factLimitsForm : (factLimits || {})} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Лимиты Runtime" icon="settings" iconVariant="info" width="1/2" fields={RUNTIME_LIMIT_FIELDS} data={factMode === 'edit' ? factLimitsForm : (factLimits || {})} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Summary Compactor"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: compactMode,
            saving: updateSummaryCompactorRole.isPending || updateCompactLimits.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setCompactForm(mapRoleToFields(summaryCompactorRole)); setCompactLimitsForm({ ...(compactLimits || {}) }); setCompactMode('edit'); },
            onSave: async () => {
              await Promise.all([
                updateSummaryCompactorRole.mutateAsync(compactForm),
                updateCompactLimits.mutateAsync(toLimitsUpdate(compactLimitsForm)),
              ]);
              setCompactMode('view');
            },
            onCancel: () => { setCompactMode('view'); setCompactForm(DEFAULT_ROLE_FORM); setCompactLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedSummaryCompactorFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={compactMode === 'edit' ? compactForm : mapRoleToFields(summaryCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedSummaryCompactorFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={compactMode === 'edit' ? compactForm : mapRoleToFields(summaryCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
          {canEditOutputRequirements(summaryCompactorRole?.response_contract) ? (
            <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedSummaryCompactorFields.filter((f) => f.key === 'output_requirements')} data={compactMode === 'edit' ? compactForm : mapRoleToFields(summaryCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
          ) : null}
          <Block title="Лимиты LLM" icon="zap" iconVariant="warning" width="1/2" fields={LLM_LIMIT_FIELDS} data={compactMode === 'edit' ? compactLimitsForm : (compactLimits || {})} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Лимиты Runtime" icon="settings" iconVariant="info" width="1/2" fields={RUNTIME_LIMIT_FIELDS} data={compactMode === 'edit' ? compactLimitsForm : (compactLimits || {})} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactLimitsForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>
      </EntityPageV2>

      {(modelsLoading || plannerLoading || synthesizerLoading || factExtractorLoading || summaryCompactorLoading || plannerLimitsLoading || synthLimitsLoading || factLimitsLoading || compactLimitsLoading) && (
        <div>Загрузка настроек оркестрации…</div>
      )}
    </>
  );
}

export default OrchestrationPage;

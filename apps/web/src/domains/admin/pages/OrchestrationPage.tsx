import { useMemo, useState } from 'react';

import type { ActorLimits, Model, ResponseContract, SystemLLMRole, SystemLLMRoleUpdate } from '@/shared/api/admin';
import { useModels } from '@/shared/api/hooks/useAdmin';
import {
  useActiveFactExtractorRole,
  useActivePlannerRole,
  useActiveTurnPreflightRole,
  useActiveFactCompactorRole,
  useActiveDocumentMemoryExtractorRole,
  useActiveSynthesizerRole,
  useOrchestratorExecutionLimits,
  useUpdateOrchestratorRoleSettings,
  useUpdateDocumentMemoryExtractorRole,
} from '@/shared/api/hooks/usePlatformSettings';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, EntityPageV2, Input, Tab } from '@/shared/ui';
import type { GridFieldConfig as FieldConfig } from '@/shared/ui';
import { ContractAwareEditor } from '@/shared/ui/ContractAwareEditor/ContractAwareEditor';
import {
  FACT_EXTRACTOR_INPUT_CONTRACT,
  PLANNER_INPUT_CONTRACT,
  TURN_PREFLIGHT_INPUT_CONTRACT,
  FACT_COMPACTOR_INPUT_CONTRACT,
  SYNTHESIZER_INPUT_CONTRACT,
} from '@/shared/constants/orchestratorContracts';

const ROLE_PARAM_KEYS = ['model', 'temperature'];
const ROLE_AUXILIARY_KEYS = ['examples'];

type RoleFormData = SystemLLMRoleUpdate & Record<string, unknown>;

const DEFAULT_ROLE_FORM: RoleFormData = {
  identity: '',
  mission: '',
  rules: '',
  safety: '',
  output_requirements: '',
  examples: [],
  extras: {},
  model: '',
  temperature: null,
};

const DOCUMENT_PROMPT_KEYS = {
  screening: 'document_memory_screening_prompt',
  study: 'document_memory_study_prompt',
  conflict: 'document_memory_conflict_prompt',
} as const;

type DocumentMemoryRoleForm = RoleFormData & {
  screening_prompt: string;
  study_prompt: string;
  conflict_prompt: string;
};

const DEFAULT_DOCUMENT_MEMORY_ROLE_FORM: DocumentMemoryRoleForm = {
  ...DEFAULT_ROLE_FORM,
  screening_prompt: '',
  study_prompt: '',
  conflict_prompt: '',
};

const DOCUMENT_MEMORY_PROMPT_FIELDS: FieldConfig[] = [
  { key: 'screening_prompt', label: 'Первичная оценка', type: 'textarea', rows: 8, description: 'Промпт, который решает: изучать документ, пропустить или передать на проверку.' },
  { key: 'study_prompt', label: 'Извлечение из секций', type: 'textarea', rows: 12, description: 'Промпт для извлечения кандидатов памяти из очередного batch секций.' },
  { key: 'conflict_prompt', label: 'Проверка конфликта', type: 'textarea', rows: 8, description: 'Промпт для сравнения нового кандидата с существующим знанием.' },
];

const ORCHESTRATOR_LIMIT_FIELDS: FieldConfig[] = [
  { key: 'llm_calls_max', label: 'LLM-вызовы', description: 'Максимум запросов к модели в фазе. Настройка сохраняется сейчас; runtime начнёт её применять отдельным этапом.' },
  { key: 'wall_time_ms_max', label: 'Таймаут фазы (мс)', description: 'Максимальная длительность фазы. Таймаут одного запроса и размер контекста настраиваются у модели. Настройка пока только сохраняется.' },
].map((field) => ({
  ...field,
  type: 'custom',
  description: field.description,
  render: (value, editable, onChange) => editable ? (
    <Input type="number" min={1} step={1} value={value == null ? '' : String(value)}
      onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))} />
  ) : <span>{value == null ? '—' : String(value)}</span>,
}));

const FACT_POLICY_FIELD: FieldConfig = {
  key: 'extras', label: 'Политика отбора фактов', type: 'json', rows: 6,
  description: 'Необязательные настройки: max_facts_per_turn, max_subject_len, max_value_len, max_value_words, confidence_min. Отсутствующие значения используют defaults экстрактора.',
};

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
  {
    key: 'temperature', label: 'Temperature', type: 'custom',
    description: 'От 0 до 2. Пустое значение оставляет температуру на усмотрение модели.',
    render: (value, editable, onChange) => editable ? (
      <Input aria-label="Temperature" type="number" min={0} max={2} step="any"
        value={value == null ? '' : String(value)}
        onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))} />
    ) : <span>{value == null ? 'По умолчанию модели' : String(value)}</span>,
  },
  { key: 'examples', label: 'Примеры', type: 'json', rows: 8, description: 'Примеры добавляются в промпт. Массив объектов с input, output и необязательным description. Пустой массив допустим.' },
];

function mapRoleToFields(role?: SystemLLMRole): RoleFormData {
  return {
    identity: role?.identity ?? DEFAULT_ROLE_FORM.identity,
    mission: role?.mission ?? DEFAULT_ROLE_FORM.mission,
    rules: role?.rules ?? DEFAULT_ROLE_FORM.rules,
    safety: role?.safety ?? DEFAULT_ROLE_FORM.safety,
    output_requirements: role?.output_requirements ?? DEFAULT_ROLE_FORM.output_requirements,
    examples: role?.examples ?? DEFAULT_ROLE_FORM.examples,
    extras: role?.extras ?? DEFAULT_ROLE_FORM.extras,
    model: role?.model ?? DEFAULT_ROLE_FORM.model,
    temperature: role?.temperature ?? null,
  };
}

function mapDocumentMemoryRoleToFields(role?: SystemLLMRole): DocumentMemoryRoleForm {
  const base = mapRoleToFields(role);
  const extras = role?.extras ?? {};
  const prompt = (key: string): string => typeof extras[key] === 'string' ? extras[key] as string : '';
  return {
    ...base,
    screening_prompt: prompt(DOCUMENT_PROMPT_KEYS.screening),
    study_prompt: prompt(DOCUMENT_PROMPT_KEYS.study),
    conflict_prompt: prompt(DOCUMENT_PROMPT_KEYS.conflict),
  };
}

function documentMemoryRoleUpdate(form: DocumentMemoryRoleForm): SystemLLMRoleUpdate {
  const { screening_prompt, study_prompt, conflict_prompt, ...role } = form;
  return {
    ...role,
    extras: {
      ...(role.extras as Record<string, unknown>),
      [DOCUMENT_PROMPT_KEYS.screening]: screening_prompt,
      [DOCUMENT_PROMPT_KEYS.study]: study_prompt,
      [DOCUMENT_PROMPT_KEYS.conflict]: conflict_prompt,
    },
  };
}

export function OrchestrationPage() {
  const [plannerMode, setPlannerMode] = useState<'view' | 'edit'>('view');
  const [plannerForm, setPlannerForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [plannerLimitsForm, setPlannerLimitsForm] = useState<Record<string, unknown>>({});
  const [preflightMode, setPreflightMode] = useState<'view' | 'edit'>('view');
  const [preflightForm, setPreflightForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [preflightLimitsForm, setPreflightLimitsForm] = useState<Record<string, unknown>>({});

  const [synthMode, setSynthMode] = useState<'view' | 'edit'>('view');
  const [synthForm, setSynthForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [synthLimitsForm, setSynthLimitsForm] = useState<Record<string, unknown>>({});

  const [factMode, setFactMode] = useState<'view' | 'edit'>('view');
  const [factForm, setFactForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [factLimitsForm, setFactLimitsForm] = useState<Record<string, unknown>>({});

  const [compactMode, setCompactMode] = useState<'view' | 'edit'>('view');
  const [compactForm, setCompactForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [compactLimitsForm, setCompactLimitsForm] = useState<Record<string, unknown>>({});

  const [documentStudyMode, setDocumentStudyMode] = useState<'view' | 'edit'>('view');
  const [documentStudyForm, setDocumentStudyForm] = useState<DocumentMemoryRoleForm>(DEFAULT_DOCUMENT_MEMORY_ROLE_FORM);

  const { data: plannerRole, isLoading: plannerLoading } = useActivePlannerRole();
  const { data: preflightRole, isLoading: preflightLoading } = useActiveTurnPreflightRole();
  const { data: synthesizerRole, isLoading: synthesizerLoading } = useActiveSynthesizerRole();
  const { data: factExtractorRole, isLoading: factExtractorLoading } = useActiveFactExtractorRole();
  const { data: factCompactorRole, isLoading: factCompactorLoading } = useActiveFactCompactorRole();
  const { data: documentStudyRole, isLoading: documentStudyLoading } = useActiveDocumentMemoryExtractorRole();

  const { data: plannerLimits, isLoading: plannerLimitsLoading } = useOrchestratorExecutionLimits('planner');
  const { data: preflightLimits, isLoading: preflightLimitsLoading } = useOrchestratorExecutionLimits('turn_preflight');
  const { data: synthLimits, isLoading: synthLimitsLoading } = useOrchestratorExecutionLimits('synthesizer');
  const { data: factLimits, isLoading: factLimitsLoading } = useOrchestratorExecutionLimits('fact_extractor');
  const { data: compactLimits, isLoading: compactLimitsLoading } = useOrchestratorExecutionLimits('fact_compactor');

  const updatePlannerSettings = useUpdateOrchestratorRoleSettings('planner');
  const updatePreflightSettings = useUpdateOrchestratorRoleSettings('turn_preflight');
  const updateSynthesizerSettings = useUpdateOrchestratorRoleSettings('synthesizer');
  const updateFactExtractorSettings = useUpdateOrchestratorRoleSettings('fact_extractor');
  const updateFactCompactorSettings = useUpdateOrchestratorRoleSettings('fact_compactor');
  const updateDocumentStudyRole = useUpdateDocumentMemoryExtractorRole();

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
  const resolvedPreflightFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Корневой маршрутизатор turn до planner/synthesizer.',
    mission: 'Определяет единственный следующий маршрут и нормализует задачу.',
    rules: 'Не выполняет инструменты и не создаёт план; может запросить recall или clarification.',
    safety: 'Не считать кандидатов записанными в память и не утверждать недоказанные факты.',
    outputRequirements: 'Строгий TurnPreflightDecision с ровно одним route payload.',
    model: 'LLM-модель preflight.',
  }, preflightRole?.response_contract ?? null, TURN_PREFLIGHT_INPUT_CONTRACT), [modelOptions, preflightRole?.response_contract]);
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
  const resolvedFactCompactorFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль компактора подтверждённых фактов.',
    mission: 'Нормализация и объединение кандидатов фактов перед сохранением.',
    rules: 'Правила слияния candidates и обязательной привязки source_candidate_indexes.',
    safety: 'Ограничения на создание новых или неподтверждённых сведений.',
    outputRequirements: 'Требования к JSON-результату нормализации фактов.',
    model: 'LLM-модель fact compactor.',
  }, factCompactorRole?.response_contract ?? null, FACT_COMPACTOR_INPUT_CONTRACT), [modelOptions, factCompactorRole?.response_contract]);

  const toLimitsUpdate = (form: Record<string, unknown>): ActorLimits => ({
    llm_calls_max: form.llm_calls_max as number | null | undefined,
    wall_time_ms_max: form.wall_time_ms_max as number | null | undefined,
  });

  return (
    <>
      <EntityPageV2
        title="Оркестрация"
        mode="view"
        loading={modelsLoading || plannerLoading || preflightLoading || synthesizerLoading || factExtractorLoading || factCompactorLoading || documentStudyLoading || plannerLimitsLoading || preflightLimitsLoading || synthLimitsLoading || factLimitsLoading || compactLimitsLoading}
        breadcrumbs={[{ label: 'Оркестрация' }]}
      >
        <Tab
          title="Планировщик"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: plannerMode,
            saving: updatePlannerSettings.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => {
              setPlannerForm(mapRoleToFields(plannerRole));
              setPlannerLimitsForm({ ...(plannerLimits?.own || {}) });
              setPlannerMode('edit');
            },
            onSave: async () => {
              await updatePlannerSettings.mutateAsync({
                ...plannerForm,
                execution_limits: toLimitsUpdate(plannerLimitsForm),
              });
              setPlannerMode('view');
            },
            onCancel: () => { setPlannerMode('view'); setPlannerForm(DEFAULT_ROLE_FORM); setPlannerLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedPlannerFields.filter((f) => ['identity', 'mission', 'rules', 'safety'].includes(f.key))} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={[...resolvedPlannerFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key)), ...ORCHESTRATOR_LIMIT_FIELDS]} data={plannerMode === 'edit' ? { ...plannerForm, ...plannerLimitsForm } : { ...mapRoleToFields(plannerRole), ...plannerLimits?.own }} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => { if (ORCHESTRATOR_LIMIT_FIELDS.some((field) => field.key === k)) setPlannerLimitsForm((p) => ({ ...p, [k]: v })); else setPlannerForm((p) => ({ ...p, [k]: v })); } : undefined} />
          <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedPlannerFields.filter((f) => f.key === 'output_requirements')} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Примеры" icon="code" iconVariant="info" width="full" fields={resolvedPlannerFields.filter((f) => ROLE_AUXILIARY_KEYS.includes(f.key))} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Маршрутизатор запроса"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: preflightMode,
            saving: updatePreflightSettings.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setPreflightForm(mapRoleToFields(preflightRole)); setPreflightLimitsForm({ ...(preflightLimits?.own || {}) }); setPreflightMode('edit'); },
            onSave: async () => {
              await updatePreflightSettings.mutateAsync({ ...preflightForm, execution_limits: toLimitsUpdate(preflightLimitsForm) });
              setPreflightMode('view');
            },
            onCancel: () => { setPreflightMode('view'); setPreflightForm(DEFAULT_ROLE_FORM); setPreflightLimitsForm({}); },
          })}
        >
          <Block title="Правила маршрутизации" icon="shield" iconVariant="primary" width="2/3" fields={resolvedPreflightFields.filter((f) => ['identity', 'mission', 'rules', 'safety'].includes(f.key))} data={preflightMode === 'edit' ? preflightForm : mapRoleToFields(preflightRole)} editable={preflightMode === 'edit'} onChange={preflightMode === 'edit' ? (k, v) => setPreflightForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={[...resolvedPreflightFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key)), ...ORCHESTRATOR_LIMIT_FIELDS]} data={preflightMode === 'edit' ? { ...preflightForm, ...preflightLimitsForm } : { ...mapRoleToFields(preflightRole), ...preflightLimits?.own }} editable={preflightMode === 'edit'} onChange={preflightMode === 'edit' ? (k, v) => { if (ORCHESTRATOR_LIMIT_FIELDS.some((field) => field.key === k)) setPreflightLimitsForm((p) => ({ ...p, [k]: v })); else setPreflightForm((p) => ({ ...p, [k]: v })); } : undefined} />
          <Block title="Контракт ответа" icon="code" iconVariant="warning" width="full" fields={resolvedPreflightFields.filter((f) => f.key === 'output_requirements')} data={preflightMode === 'edit' ? preflightForm : mapRoleToFields(preflightRole)} editable={preflightMode === 'edit'} onChange={preflightMode === 'edit' ? (k, v) => setPreflightForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Примеры" icon="code" iconVariant="info" width="full" fields={resolvedPreflightFields.filter((f) => ROLE_AUXILIARY_KEYS.includes(f.key))} data={preflightMode === 'edit' ? preflightForm : mapRoleToFields(preflightRole)} editable={preflightMode === 'edit'} onChange={preflightMode === 'edit' ? (k, v) => setPreflightForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Синтезатор ответа"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: synthMode,
            saving: updateSynthesizerSettings.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setSynthForm(mapRoleToFields(synthesizerRole)); setSynthLimitsForm({ ...(synthLimits?.own || {}) }); setSynthMode('edit'); },
            onSave: async () => {
              await updateSynthesizerSettings.mutateAsync({
                ...synthForm,
                execution_limits: toLimitsUpdate(synthLimitsForm),
              });
              setSynthMode('view');
            },
            onCancel: () => { setSynthMode('view'); setSynthForm(DEFAULT_ROLE_FORM); setSynthLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedSynthesizerFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={[...resolvedSynthesizerFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key)), ...ORCHESTRATOR_LIMIT_FIELDS]} data={synthMode === 'edit' ? { ...synthForm, ...synthLimitsForm } : { ...mapRoleToFields(synthesizerRole), ...synthLimits?.own }} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => { if (ORCHESTRATOR_LIMIT_FIELDS.some((field) => field.key === k)) setSynthLimitsForm((p) => ({ ...p, [k]: v })); else setSynthForm((p) => ({ ...p, [k]: v })); } : undefined} />
          <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedSynthesizerFields.filter((f) => f.key === 'output_requirements')} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Примеры" icon="code" iconVariant="info" width="full" fields={resolvedSynthesizerFields.filter((f) => ROLE_AUXILIARY_KEYS.includes(f.key))} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Экстрактор фактов"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: factMode,
            saving: updateFactExtractorSettings.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setFactForm(mapRoleToFields(factExtractorRole)); setFactLimitsForm({ ...(factLimits?.own || {}) }); setFactMode('edit'); },
            onSave: async () => {
              await updateFactExtractorSettings.mutateAsync({ ...factForm, execution_limits: toLimitsUpdate(factLimitsForm) });
              setFactMode('view');
            },
            onCancel: () => { setFactMode('view'); setFactForm(DEFAULT_ROLE_FORM); setFactLimitsForm({}); },
          })}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedFactExtractorFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={[...resolvedFactExtractorFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key)), ...ORCHESTRATOR_LIMIT_FIELDS, FACT_POLICY_FIELD]} data={factMode === 'edit' ? { ...factForm, ...factLimitsForm } : { ...mapRoleToFields(factExtractorRole), ...factLimits?.own }} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => { if (ORCHESTRATOR_LIMIT_FIELDS.some((field) => field.key === k)) setFactLimitsForm((p) => ({ ...p, [k]: v })); else setFactForm((p) => ({ ...p, [k]: v })); } : undefined} />
          <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedFactExtractorFields.filter((f) => f.key === 'output_requirements')} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Примеры" icon="code" iconVariant="info" width="full" fields={resolvedFactExtractorFields.filter((f) => ROLE_AUXILIARY_KEYS.includes(f.key))} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Нормализатор фактов"
          layout="grid"
          actions={buildEntityCrudActions({
            mode: compactMode,
            saving: updateFactCompactorSettings.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setCompactForm(mapRoleToFields(factCompactorRole)); setCompactLimitsForm({ ...(compactLimits?.own || {}) }); setCompactMode('edit'); },
            onSave: async () => {
              await updateFactCompactorSettings.mutateAsync({ ...compactForm, execution_limits: toLimitsUpdate(compactLimitsForm) });
              setCompactMode('view');
            },
            onCancel: () => { setCompactMode('view'); setCompactForm(DEFAULT_ROLE_FORM); setCompactLimitsForm({}); },
          })}
        >
          {/* Статус: используется после хода для проверки и нормализации подтверждённых user/tenant facts. */}
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedFactCompactorFields.filter((f) => f.key === 'identity' || f.key === 'mission' || f.key === 'rules' || f.key === 'safety')} data={compactMode === 'edit' ? compactForm : mapRoleToFields(factCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={[...resolvedFactCompactorFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key)), ...ORCHESTRATOR_LIMIT_FIELDS]} data={compactMode === 'edit' ? { ...compactForm, ...compactLimitsForm } : { ...mapRoleToFields(factCompactorRole), ...compactLimits?.own }} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => { if (ORCHESTRATOR_LIMIT_FIELDS.some((field) => field.key === k)) setCompactLimitsForm((p) => ({ ...p, [k]: v })); else setCompactForm((p) => ({ ...p, [k]: v })); } : undefined} />
          <Block title="Критерии ответа" icon="code" iconVariant="warning" width="full" fields={resolvedFactCompactorFields.filter((f) => f.key === 'output_requirements')} data={compactMode === 'edit' ? compactForm : mapRoleToFields(factCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Примеры" icon="code" iconVariant="info" width="full" fields={resolvedFactCompactorFields.filter((f) => ROLE_AUXILIARY_KEYS.includes(f.key))} data={compactMode === 'edit' ? compactForm : mapRoleToFields(factCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        {/* DEPRECATED: this role serves only the legacy shadow document study/review pipeline. */}
        <Tab
          title="Изучатель документов"
          hidden
          layout="grid"
          actions={buildEntityCrudActions({
            mode: documentStudyMode,
            saving: updateDocumentStudyRole.isPending,
            tone: 'default',
            labels: { edit: 'Изменить' },
            onEdit: () => { setDocumentStudyForm(mapDocumentMemoryRoleToFields(documentStudyRole)); setDocumentStudyMode('edit'); },
            onSave: async () => {
              await updateDocumentStudyRole.mutateAsync(documentMemoryRoleUpdate(documentStudyForm));
              setDocumentStudyMode('view');
            },
            onCancel: () => { setDocumentStudyMode('view'); setDocumentStudyForm(DEFAULT_DOCUMENT_MEMORY_ROLE_FORM); },
          })}
        >
          <Block title="Промпты этапов" icon="shield" iconVariant="primary" width="2/3" fields={DOCUMENT_MEMORY_PROMPT_FIELDS} data={documentStudyMode === 'edit' ? documentStudyForm : mapDocumentMemoryRoleToFields(documentStudyRole)} editable={documentStudyMode === 'edit'} onChange={documentStudyMode === 'edit' ? (key, value) => setDocumentStudyForm((form) => ({ ...form, [key]: value })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={roleFields(modelOptions, { identity: '', mission: '', rules: '', safety: '', outputRequirements: '', model: 'LLM-модель изучателя документов.' }, documentStudyRole?.response_contract ?? null, null).filter((field) => ROLE_PARAM_KEYS.includes(field.key))} data={documentStudyMode === 'edit' ? documentStudyForm : mapDocumentMemoryRoleToFields(documentStudyRole)} editable={documentStudyMode === 'edit'} onChange={documentStudyMode === 'edit' ? (key, value) => setDocumentStudyForm((form) => ({ ...form, [key]: value })) : undefined} />
        </Tab>
      </EntityPageV2>

    </>
  );
}

export default OrchestrationPage;

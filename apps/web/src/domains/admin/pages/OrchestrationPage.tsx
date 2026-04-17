import { useMemo, useState } from 'react';
import { useModels } from '@/shared/api/hooks/useAdmin';
import type { Model, SystemLLMRole, SystemLLMRoleUpdate } from '@/shared/api/admin';
import {
  useOrchestrationSettings,
  useUpdateOrchestrationSettings,
  useActiveTriageRole,
  useActivePlannerRole,
  useActiveSummaryRole,
  useActiveMemoryRole,
  useUpdateTriageRole,
  useUpdatePlannerRole,
  useUpdateSummaryRole,
  useUpdateMemoryRole,
} from '@/shared/api/hooks/usePlatformSettings';
import { EntityPageV2, Tab } from '@/shared/ui';
import { Block } from '@/shared/ui';
import { Button } from '@/shared/ui';
import { ConfirmDialog } from '@/shared/ui';
import type { GridFieldConfig as FieldConfig } from '@/shared/ui';

// Field configurations for orchestration settings
const executorFields = (modelOptions: Array<{ value: string; label: string }>): FieldConfig[] => [
  {
    key: 'executor_model',
    label: 'Модель исполнителя',
    type: 'select',
    options: modelOptions,
    description: 'LLM-модель, которой выполняются шаги выполнения.',
  },
  {
    key: 'executor_temperature',
    label: 'Temperature исполнителя',
    type: 'number',
    description: 'Степень вариативности ответа исполнителя.',
    placeholder: 'Пример: 0.3',
  },
  {
    key: 'executor_timeout_s',
    label: 'Таймаут по умолчанию (сек)',
    type: 'number',
    description: 'Ограничение времени одного вызова исполнителя.',
    placeholder: 'Пример: 60',
  },
  {
    key: 'executor_max_steps',
    label: 'Макс. шагов',
    type: 'number',
    description: 'Ограничение числа шагов планера на один запуск.',
    placeholder: 'Пример: 10',
  },
  {
    key: 'triage_fail_open',
    label: 'Triage fail-open',
    type: 'boolean',
    description: 'Если triage падает, продолжаем выполнение через orchestrate.',
  },
  {
    key: 'preflight_fail_open',
    label: 'Preflight fail-open',
    type: 'boolean',
    description: 'Если preflight недоступен, продолжаем выполнение с предупреждением.',
  },
  {
    key: 'preflight_fail_open_message',
    label: 'Сообщение preflight fail-open',
    type: 'textarea',
    rows: 3,
    description: 'Текст уведомления пользователю при fail-open на preflight.',
    placeholder: 'Пример: Проверка доступности агентов временно недоступна, продолжаю выполнение.',
  },
  {
    key: 'planner_fail_open',
    label: 'Planner fail-open',
    type: 'boolean',
    description: 'Если planner падает, завершаем с мягким сообщением без ошибки.',
  },
  {
    key: 'planner_fail_open_message',
    label: 'Сообщение planner fail-open',
    type: 'textarea',
    rows: 3,
    description: 'Текст уведомления пользователю при fail-open на planner.',
    placeholder: 'Пример: Планировщик временно недоступен, попробуйте повторить запрос позже.',
  },
];

// SystemLLMRole field configurations
const triageFields = (modelOptions: Array<{ value: string; label: string }>): FieldConfig[] => [
  {
    key: 'identity',
    label: 'Идентичность',
    type: 'textarea',
    rows: 4,
    description: 'Кто такой triage-агент и какую роль он выполняет.',
    placeholder: 'Пример: Ты triage-агент корпоративного AI-портала.',
  },
  {
    key: 'mission',
    label: 'Миссия',
    type: 'textarea',
    rows: 8,
    description: 'Что должен делать агент на этапе первичной маршрутизации.',
    placeholder: 'Пример: Определи, нужно ответить сразу, уточнить или отправить в оркестрацию.',
  },
  {
    key: 'rules',
    label: 'Правила',
    type: 'textarea',
    rows: 6,
    description: 'Детальные правила принятия решения final/clarify/orchestrate.',
    placeholder: 'Пример: Если запрос связан с внутренними системами — выбирай orchestrate.',
  },
  {
    key: 'safety',
    label: 'Безопасность',
    type: 'textarea',
    rows: 4,
    description: 'Ограничения безопасности для triage.',
    placeholder: 'Пример: Не выдавай final для рискованных или операционных запросов.',
  },
  {
    key: 'output_requirements',
    label: 'Требования к выходу',
    type: 'textarea',
    rows: 4,
    description: 'Формат выходного JSON и обязательные поля.',
    placeholder: 'Пример: Верни только JSON с полями type, confidence, reason, answer/clarify_prompt/goal.',
  },
  {
    key: 'model',
    label: 'Модель',
    type: 'select',
    options: modelOptions,
    description: 'LLM-модель для triage. Пример: `llm.gpt-4o-mini`.',
  },
  {
    key: 'temperature',
    label: 'Temperature',
    type: 'number',
    description: 'Степень вариативности ответа.',
    placeholder: 'Пример: 0.3',
  },
  {
    key: 'max_tokens',
    label: 'Макс. токенов',
    type: 'number',
    description: 'Максимальный размер ответа модели.',
    placeholder: 'Пример: 1000',
  },
  {
    key: 'timeout_s',
    label: 'Таймаут (сек)',
    type: 'number',
    description: 'Ограничение времени одного вызова модели.',
    placeholder: 'Пример: 10',
  },
  {
    key: 'max_retries',
    label: 'Макс. попыток',
    type: 'number',
    description: 'Сколько раз повторять запрос при ошибке.',
    placeholder: 'Пример: 2',
  },
  { 
    key: 'retry_backoff', 
    label: 'Стратегия backoff', 
    type: 'select', 
    description: 'Пауза между повторами. Пример: linear.',
    options: [
      { value: 'none', label: 'Без паузы' },
      { value: 'linear', label: 'Линейная' },
      { value: 'exp', label: 'Экспоненциальная' },
    ]
  },
];

const plannerFields = (modelOptions: Array<{ value: string; label: string }>): FieldConfig[] => [
  {
    key: 'identity',
    label: 'Идентичность',
    type: 'textarea',
    rows: 4,
    description: 'Роль planner-агента в процессе выполнения.',
    placeholder: 'Пример: Ты planner-агент, который выбирает следующий шаг выполнения.',
  },
  {
    key: 'mission',
    label: 'Миссия',
    type: 'textarea',
    rows: 8,
    description: 'Главная цель планировщика на каждом шаге.',
    placeholder: 'Пример: Декомпозируй цель на минимальный следующий шаг и делегируй агенту.',
  },
  {
    key: 'rules',
    label: 'Правила',
    type: 'textarea',
    rows: 6,
    description: 'Логика переходов между фазами и выбора действий.',
    placeholder: 'Пример: Не повторяй уже выполненные шаги и не пропускай must_do фазы.',
  },
  {
    key: 'safety',
    label: 'Безопасность',
    type: 'textarea',
    rows: 6,
    description: 'Ограничения и контроль риска для планирования.',
    placeholder: 'Пример: Для рискованных операций требуй подтверждение.',
  },
  {
    key: 'output_requirements',
    label: 'Требования к выходу',
    type: 'textarea',
    rows: 4,
    description: 'Строгий формат JSON-плана (goal + steps).',
    placeholder: 'Пример: Верни JSON с goal и массивом steps, где каждый шаг содержит kind/ref/input.',
  },
  {
    key: 'model',
    label: 'Модель',
    type: 'select',
    options: modelOptions,
    description: 'LLM-модель для planner. Пример: `llm.llama.maverick`.',
  },
  {
    key: 'temperature',
    label: 'Temperature',
    type: 'number',
    description: 'Степень вариативности генерации плана.',
    placeholder: 'Пример: 0.2',
  },
  {
    key: 'max_tokens',
    label: 'Макс. токенов',
    type: 'number',
    description: 'Лимит токенов на один ответ planner.',
    placeholder: 'Пример: 4096',
  },
  {
    key: 'timeout_s',
    label: 'Таймаут (сек)',
    type: 'number',
    description: 'Максимальное время ожидания ответа от модели.',
    placeholder: 'Пример: 60',
  },
  {
    key: 'max_retries',
    label: 'Макс. попыток',
    type: 'number',
    description: 'Число повторов при временной ошибке.',
    placeholder: 'Пример: 2',
  },
  { 
    key: 'retry_backoff', 
    label: 'Стратегия backoff', 
    type: 'select', 
    description: 'Пауза между повторами. Пример: linear.',
    options: [
      { value: 'none', label: 'Без паузы' },
      { value: 'linear', label: 'Линейная' },
      { value: 'exp', label: 'Экспоненциальная' },
    ]
  },
];

const summaryFields = (modelOptions: Array<{ value: string; label: string }>): FieldConfig[] => [
  {
    key: 'identity',
    label: 'Идентичность',
    type: 'textarea',
    rows: 4,
    description: 'Роль summary-агента в пайплайне.',
    placeholder: 'Пример: Ты summary-агент, который сжимает контекст диалога.',
  },
  {
    key: 'mission',
    label: 'Миссия',
    type: 'textarea',
    rows: 6,
    description: 'Что именно должно попасть в итоговое резюме.',
    placeholder: 'Пример: Выделяй цель, результат, риски и открытые вопросы.',
  },
  {
    key: 'rules',
    label: 'Правила',
    type: 'textarea',
    rows: 6,
    description: 'Правила отбора и компрессии информации.',
    placeholder: 'Пример: Не добавляй неподтвержденные факты и не теряй ключевые выводы.',
  },
  {
    key: 'safety',
    label: 'Безопасность',
    type: 'textarea',
    rows: 4,
    description: 'Ограничения по чувствительным данным.',
    placeholder: 'Пример: Не включай пароли, токены и внутренние секреты.',
  },
  {
    key: 'output_requirements',
    label: 'Требования к выходу',
    type: 'textarea',
    rows: 4,
    description: 'Требуемый формат результата summary.',
    placeholder: 'Пример: Верни короткий связный текст на русском без markdown.',
  },
  {
    key: 'model',
    label: 'Модель',
    type: 'select',
    options: modelOptions,
    description: 'LLM-модель для summary. Пример: `llm.gpt-4o-mini`.',
  },
  {
    key: 'temperature',
    label: 'Temperature',
    type: 'number',
    description: 'Креативность при формировании summary.',
    placeholder: 'Пример: 0.1',
  },
  {
    key: 'max_tokens',
    label: 'Макс. токенов',
    type: 'number',
    description: 'Лимит длины summary-ответа.',
    placeholder: 'Пример: 1500',
  },
  {
    key: 'timeout_s',
    label: 'Таймаут (сек)',
    type: 'number',
    description: 'Максимальное время генерации summary.',
    placeholder: 'Пример: 10',
  },
  {
    key: 'max_retries',
    label: 'Макс. попыток',
    type: 'number',
    description: 'Количество повторов при ошибке модели.',
    placeholder: 'Пример: 2',
  },
  { 
    key: 'retry_backoff', 
    label: 'Стратегия backoff', 
    type: 'select', 
    description: 'Пауза между повторами. Пример: linear.',
    options: [
      { value: 'none', label: 'Без паузы' },
      { value: 'linear', label: 'Линейная' },
      { value: 'exp', label: 'Экспоненциальная' },
    ]
  },
];

const memoryFields = (modelOptions: Array<{ value: string; label: string }>): FieldConfig[] => [
  {
    key: 'identity',
    label: 'Идентичность',
    type: 'textarea',
    rows: 4,
    description: 'Роль memory-агента в рантайме.',
    placeholder: 'Пример: Ты memory-агент, поддерживающий рабочую память выполнения.',
  },
  {
    key: 'mission',
    label: 'Миссия',
    type: 'textarea',
    rows: 6,
    description: 'Какие данные memory должен аккумулировать.',
    placeholder: 'Пример: Сохраняй факты, открытые вопросы, риски и next actions.',
  },
  {
    key: 'rules',
    label: 'Правила',
    type: 'textarea',
    rows: 6,
    description: 'Правила обновления и очистки памяти.',
    placeholder: 'Пример: Не дублируй факты, удаляй шум, помечай неопределенность.',
  },
  {
    key: 'safety',
    label: 'Безопасность',
    type: 'textarea',
    rows: 4,
    description: 'Что запрещено сохранять в memory.',
    placeholder: 'Пример: Не сохраняй секреты, токены, пароли и персональные данные.',
  },
  {
    key: 'output_requirements',
    label: 'Требования к выходу',
    type: 'textarea',
    rows: 4,
    description: 'Формат структуры memory.',
    placeholder: 'Пример: Верни JSON с массивами facts/open_questions/risks/next_actions.',
  },
  {
    key: 'model',
    label: 'Модель',
    type: 'select',
    options: modelOptions,
    description: 'LLM-модель для memory. Пример: `llm.gpt-4o-mini`.',
  },
  {
    key: 'temperature',
    label: 'Temperature',
    type: 'number',
    description: 'Креативность обновления памяти.',
    placeholder: 'Пример: 0.1',
  },
  {
    key: 'max_tokens',
    label: 'Макс. токенов',
    type: 'number',
    description: 'Лимит токенов на один ответ memory.',
    placeholder: 'Пример: 1200',
  },
  {
    key: 'timeout_s',
    label: 'Таймаут (сек)',
    type: 'number',
    description: 'Время ожидания ответа memory.',
    placeholder: 'Пример: 10',
  },
  {
    key: 'max_retries',
    label: 'Макс. попыток',
    type: 'number',
    description: 'Количество повторов при ошибке.',
    placeholder: 'Пример: 2',
  },
  {
    key: 'retry_backoff',
    label: 'Стратегия backoff',
    type: 'select',
    description: 'Пауза между повторами. Пример: linear.',
    options: [
      { value: 'none', label: 'Без паузы' },
      { value: 'linear', label: 'Линейная' },
      { value: 'exp', label: 'Экспоненциальная' },
    ],
  },
];

type RoleFormData = SystemLLMRoleUpdate & Record<string, unknown>;

const DEFAULT_ROLE_FORM: RoleFormData = {
  identity: '',
  mission: '',
  rules: '',
  safety: '',
  output_requirements: '',
  model: '',
  temperature: 0.3,
  max_tokens: 2000,
  timeout_s: 15,
  max_retries: 2,
  retry_backoff: 'linear',
};

function mapRoleToFields(role?: SystemLLMRole): RoleFormData {
  return {
    identity: role?.identity ?? DEFAULT_ROLE_FORM.identity,
    mission: role?.mission ?? DEFAULT_ROLE_FORM.mission,
    rules: role?.rules ?? DEFAULT_ROLE_FORM.rules,
    safety: role?.safety ?? DEFAULT_ROLE_FORM.safety,
    output_requirements: role?.output_requirements ?? DEFAULT_ROLE_FORM.output_requirements,
    model: role?.model ?? DEFAULT_ROLE_FORM.model,
    temperature: role?.temperature ?? DEFAULT_ROLE_FORM.temperature,
    max_tokens: role?.max_tokens ?? DEFAULT_ROLE_FORM.max_tokens,
    timeout_s: role?.timeout_s ?? DEFAULT_ROLE_FORM.timeout_s,
    max_retries: role?.max_retries ?? DEFAULT_ROLE_FORM.max_retries,
    retry_backoff: role?.retry_backoff ?? DEFAULT_ROLE_FORM.retry_backoff,
  };
}

export function OrchestrationPage() {
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingUpdates, setPendingUpdates] = useState<Record<string, unknown> | null>(null);
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  
  // Individual edit modes for SystemLLMRole tabs
  const [triageEditMode, setTriageEditMode] = useState<'view' | 'edit'>('view');
  const [plannerEditMode, setPlannerEditMode] = useState<'view' | 'edit'>('view');
  const [summaryEditMode, setSummaryEditMode] = useState<'view' | 'edit'>('view');
  const [memoryEditMode, setMemoryEditMode] = useState<'view' | 'edit'>('view');
  
  // Form data for SystemLLMRole tabs
  const [triageFormData, setTriageFormData] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [plannerFormData, setPlannerFormData] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [summaryFormData, setSummaryFormData] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [memoryFormData, setMemoryFormData] = useState<RoleFormData>(DEFAULT_ROLE_FORM);

  // Orchestration settings
  const { data: orchestrationSettings, isLoading: settingsLoading } = useOrchestrationSettings();
  const updateSettings = useUpdateOrchestrationSettings();
  
  // SystemLLMRole data
  const { data: triageRole, isLoading: triageLoading } = useActiveTriageRole();
  const { data: plannerRole, isLoading: plannerLoading } = useActivePlannerRole();
  const { data: summaryRole, isLoading: summaryLoading } = useActiveSummaryRole();
  const { data: memoryRole, isLoading: memoryLoading } = useActiveMemoryRole();
  
  const updateTriageRole = useUpdateTriageRole();
  const updatePlannerRole = useUpdatePlannerRole();
  const updateSummaryRole = useUpdateSummaryRole();
  const updateMemoryRole = useUpdateMemoryRole();
  
  const { data: modelsData, isLoading: modelsLoading } = useModels({ type: 'llm_chat', enabled_only: true });

  const modelOptions = useMemo(
    () =>
      (modelsData?.items ?? []).map((model: Model) => ({
        value: model.alias,
        label: `${model.name} (${model.alias})`,
      })),
    [modelsData]
  );

  const resolvedExecutorFields = useMemo(() => executorFields(modelOptions), [modelOptions]);
  const resolvedTriageFields = useMemo(() => triageFields(modelOptions), [modelOptions]);
  const resolvedPlannerFields = useMemo(() => plannerFields(modelOptions), [modelOptions]);
  const resolvedSummaryFields = useMemo(() => summaryFields(modelOptions), [modelOptions]);
  const resolvedMemoryFields = useMemo(() => memoryFields(modelOptions), [modelOptions]);

  // ─── Handlers ───────────────────────────────────────────────────────

  const handleEdit = () => {
    setFormData({ ...(orchestrationSettings ?? {}) });
    setMode('edit');
  };

  const handleCancel = () => {
    setFormData({});
    setMode('view');
  };

  const handleSave = async () => {
    setPendingUpdates(formData);
    setShowConfirmDialog(true);
  };

  const handleFieldChange = (key: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleConfirmSave = () => {
    if (pendingUpdates) {
      updateSettings.mutate(pendingUpdates, {
        onSuccess: () => {
          setShowConfirmDialog(false);
          setPendingUpdates(null);
          setMode('view');
        },
      });
    }
  };

  const handleCancelSave = () => {
    setShowConfirmDialog(false);
    setPendingUpdates(null);
  };

  // SystemLLMRole handlers
  const handleTriageEdit = () => {
    setTriageEditMode('edit');
    setTriageFormData(mapRoleToFields(triageRole));
  };

  const handleTriageSave = () => {
    updateTriageRole.mutate(triageFormData);
    setTriageEditMode('view');
  };

  const handleTriageCancel = () => {
    setTriageEditMode('view');
    setTriageFormData(DEFAULT_ROLE_FORM);
  };

  const handleTriageFieldChange = (key: string, value: unknown) => {
    setTriageFormData(prev => ({ ...prev, [key]: value }));
  };

  const handlePlannerEdit = () => {
    setPlannerEditMode('edit');
    setPlannerFormData(mapRoleToFields(plannerRole));
  };

  const handlePlannerSave = () => {
    updatePlannerRole.mutate(plannerFormData);
    setPlannerEditMode('view');
  };

  const handlePlannerCancel = () => {
    setPlannerEditMode('view');
    setPlannerFormData(DEFAULT_ROLE_FORM);
  };

  const handlePlannerFieldChange = (key: string, value: unknown) => {
    setPlannerFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleSummaryEdit = () => {
    setSummaryEditMode('edit');
    setSummaryFormData(mapRoleToFields(summaryRole));
  };

  const handleSummarySave = () => {
    updateSummaryRole.mutate(summaryFormData);
    setSummaryEditMode('view');
  };

  const handleSummaryCancel = () => {
    setSummaryEditMode('view');
    setSummaryFormData(DEFAULT_ROLE_FORM);
  };

  const handleSummaryFieldChange = (key: string, value: unknown) => {
    setSummaryFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleMemoryEdit = () => {
    setMemoryEditMode('edit');
    setMemoryFormData(mapRoleToFields(memoryRole));
  };

  const handleMemorySave = () => {
    updateMemoryRole.mutate(memoryFormData);
    setMemoryEditMode('view');
  };

  const handleMemoryCancel = () => {
    setMemoryEditMode('view');
    setMemoryFormData(DEFAULT_ROLE_FORM);
  };

  const handleMemoryFieldChange = (key: string, value: unknown) => {
    setMemoryFormData(prev => ({ ...prev, [key]: value }));
  };

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
          title="Исполнитель" 
          layout="grid"
          actions={
            mode === 'view' ? [
              <Button key="edit" onClick={handleEdit}>Редактировать</Button>,
            ] : mode === 'edit' ? [
              <Button 
                key="save" 
                onClick={handleSave} 
                disabled={updateSettings.isPending}
              >
                {updateSettings.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel}>Отмена</Button>,
            ] : []
          }
        >
          <Block
            title="Настройки исполнителя"
            fields={resolvedExecutorFields}
            data={mode === 'edit' ? formData : (orchestrationSettings || {})}
            editable={mode === 'edit'}
            onChange={mode === 'edit' ? handleFieldChange : undefined}
          />
        </Tab>

        <Tab 
          title="Triage" 
          layout="grid"
          actions={
            triageEditMode === 'view' ? [
              <Button key="edit" onClick={handleTriageEdit}>Редактировать</Button>,
            ] : triageEditMode === 'edit' ? [
              <Button 
                key="save" 
                onClick={handleTriageSave} 
                disabled={updateTriageRole.isPending}
              >
                {updateTriageRole.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleTriageCancel}>Отмена</Button>,
            ] : []
          }
        >
          <Block
            title="Правила"
            icon="shield"
            iconVariant="primary"
            width="2/3"
            fields={resolvedTriageFields.filter(field => 
              ['identity', 'mission', 'rules', 'safety', 'output_requirements'].includes(field.key)
            )}
            data={triageEditMode === 'edit' ? triageFormData : mapRoleToFields(triageRole)}
            editable={triageEditMode === 'edit'}
            onChange={triageEditMode === 'edit' ? handleTriageFieldChange : undefined}
          />
          <Block
            title="Параметры"
            icon="settings"
            iconVariant="info"
            width="1/3"
            fields={resolvedTriageFields.filter(field => 
              ['model', 'temperature', 'max_tokens', 'timeout_s', 'max_retries', 'retry_backoff'].includes(field.key)
            )}
            data={triageEditMode === 'edit' ? triageFormData : mapRoleToFields(triageRole)}
            editable={triageEditMode === 'edit'}
            onChange={triageEditMode === 'edit' ? handleTriageFieldChange : undefined}
          />
        </Tab>

        <Tab 
          title="Planner" 
          layout="grid"
          actions={
            plannerEditMode === 'view' ? [
              <Button key="edit" onClick={handlePlannerEdit}>Редактировать</Button>,
            ] : plannerEditMode === 'edit' ? [
              <Button 
                key="save" 
                onClick={handlePlannerSave} 
                disabled={updatePlannerRole.isPending}
              >
                {updatePlannerRole.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handlePlannerCancel}>Отмена</Button>,
            ] : []
          }
        >
          <Block
            title="Правила"
            icon="shield"
            iconVariant="primary"
            width="2/3"
            fields={resolvedPlannerFields.filter(field => 
              ['identity', 'mission', 'rules', 'safety', 'output_requirements'].includes(field.key)
            )}
            data={plannerEditMode === 'edit' ? plannerFormData : mapRoleToFields(plannerRole)}
            editable={plannerEditMode === 'edit'}
            onChange={plannerEditMode === 'edit' ? handlePlannerFieldChange : undefined}
          />
          <Block
            title="Параметры"
            icon="settings"
            iconVariant="info"
            width="1/3"
            fields={resolvedPlannerFields.filter(field => 
              ['model', 'temperature', 'max_tokens', 'timeout_s', 'max_retries', 'retry_backoff'].includes(field.key)
            )}
            data={plannerEditMode === 'edit' ? plannerFormData : mapRoleToFields(plannerRole)}
            editable={plannerEditMode === 'edit'}
            onChange={plannerEditMode === 'edit' ? handlePlannerFieldChange : undefined}
          />
        </Tab>

        <Tab 
          title="Summary" 
          layout="grid"
          actions={
            summaryEditMode === 'view' ? [
              <Button key="edit" onClick={handleSummaryEdit}>Редактировать</Button>,
            ] : summaryEditMode === 'edit' ? [
              <Button 
                key="save" 
                onClick={handleSummarySave} 
                disabled={updateSummaryRole.isPending}
              >
                {updateSummaryRole.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleSummaryCancel}>Отмена</Button>,
            ] : []
          }
        >
          <Block
            title="Правила"
            icon="shield"
            iconVariant="primary"
            width="2/3"
            fields={resolvedSummaryFields.filter(field => 
              ['identity', 'mission', 'rules', 'safety', 'output_requirements'].includes(field.key)
            )}
            data={summaryEditMode === 'edit' ? summaryFormData : mapRoleToFields(summaryRole)}
            editable={summaryEditMode === 'edit'}
            onChange={summaryEditMode === 'edit' ? handleSummaryFieldChange : undefined}
          />
          <Block
            title="Параметры"
            icon="settings"
            iconVariant="info"
            width="1/3"
            fields={resolvedSummaryFields.filter(field => 
              ['model', 'temperature', 'max_tokens', 'timeout_s', 'max_retries', 'retry_backoff'].includes(field.key)
            )}
            data={summaryEditMode === 'edit' ? summaryFormData : mapRoleToFields(summaryRole)}
            editable={summaryEditMode === 'edit'}
            onChange={summaryEditMode === 'edit' ? handleSummaryFieldChange : undefined}
          />
        </Tab>

        <Tab
          title="Memory"
          layout="grid"
          actions={
            memoryEditMode === 'view' ? [
              <Button key="edit" onClick={handleMemoryEdit}>Редактировать</Button>,
            ] : memoryEditMode === 'edit' ? [
              <Button
                key="save"
                onClick={handleMemorySave}
                disabled={updateMemoryRole.isPending}
              >
                {updateMemoryRole.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleMemoryCancel}>Отмена</Button>,
            ] : []
          }
        >
          <Block
            title="Правила"
            icon="shield"
            iconVariant="primary"
            width="2/3"
            fields={resolvedMemoryFields.filter(field =>
              ['identity', 'mission', 'rules', 'safety', 'output_requirements'].includes(field.key)
            )}
            data={memoryEditMode === 'edit' ? memoryFormData : mapRoleToFields(memoryRole)}
            editable={memoryEditMode === 'edit'}
            onChange={memoryEditMode === 'edit' ? handleMemoryFieldChange : undefined}
          />
          <Block
            title="Параметры"
            icon="settings"
            iconVariant="info"
            width="1/3"
            fields={resolvedMemoryFields.filter(field =>
              ['model', 'temperature', 'max_tokens', 'timeout_s', 'max_retries', 'retry_backoff'].includes(field.key)
            )}
            data={memoryEditMode === 'edit' ? memoryFormData : mapRoleToFields(memoryRole)}
            editable={memoryEditMode === 'edit'}
            onChange={memoryEditMode === 'edit' ? handleMemoryFieldChange : undefined}
          />
        </Tab>
      </EntityPageV2>

      {(settingsLoading || modelsLoading || triageLoading || plannerLoading || summaryLoading || memoryLoading) && <div>Загрузка настроек оркестрации…</div>}

      <ConfirmDialog
        open={showConfirmDialog}
        title="Подтвердите сохранение"
        message="Вы уверены, что хотите сохранить изменения в настройках оркестрации? Это повлияет на всех агентов и процессы выполнения."
        confirmLabel="Сохранить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={handleConfirmSave}
        onCancel={handleCancelSave}
      />
    </>
  );
}

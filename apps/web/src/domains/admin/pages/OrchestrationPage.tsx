import { useMemo, useState } from 'react';

import type { Model, SystemLLMRole, SystemLLMRoleUpdate } from '@/shared/api/admin';
import { useModels } from '@/shared/api/hooks/useAdmin';
import {
  useActiveFactExtractorRole,
  useActivePlannerRole,
  useActiveSummaryCompactorRole,
  useActiveSynthesizerRole,
  useOrchestrationSettings,
  useUpdateFactExtractorRole,
  useUpdateOrchestrationSettings,
  useUpdatePlannerRole,
  useUpdateSummaryCompactorRole,
  useUpdateSynthesizerRole,
} from '@/shared/api/hooks/usePlatformSettings';
import { Block, Button, ConfirmDialog, EntityPageV2, Tab } from '@/shared/ui';
import type { GridFieldConfig as FieldConfig } from '@/shared/ui';

const BACKOFF_OPTIONS = [
  { value: 'none', label: 'Без паузы' },
  { value: 'linear', label: 'Линейная' },
  { value: 'exp', label: 'Экспоненциальная' },
];

const ROLE_PROMPT_KEYS = ['identity', 'mission', 'rules', 'safety', 'output_requirements'];
const ROLE_PARAM_KEYS = ['model', 'temperature', 'max_tokens', 'timeout_s', 'max_retries', 'retry_backoff'];

type RoleFormData = SystemLLMRoleUpdate & Record<string, unknown>;

const DEFAULT_ROLE_FORM: RoleFormData = {
  identity: '',
  mission: '',
  rules: '',
  safety: '',
  output_requirements: '',
  model: '',
  temperature: 0.2,
  max_tokens: 2000,
  timeout_s: 30,
  max_retries: 1,
  retry_backoff: 'linear',
};

const executorFields = (modelOptions: Array<{ value: string; label: string }>): FieldConfig[] => [
  { key: 'executor_model', label: 'Модель исполнителя', type: 'select', options: modelOptions, description: 'LLM-модель, которой выполняются шаги агентского цикла.' },
  { key: 'executor_temperature', label: 'Temperature исполнителя', type: 'number', description: 'Степень вариативности ответа. Ниже — точнее, выше — креативнее.' },
];

const roleFields = (
  modelOptions: Array<{ value: string; label: string }>,
  labels: { identity: string; mission: string; rules: string; safety: string; output: string; model: string }
): FieldConfig[] => [
  { key: 'identity', label: 'Идентичность', type: 'textarea', rows: 4, description: labels.identity },
  { key: 'mission', label: 'Миссия', type: 'textarea', rows: 6, description: labels.mission },
  { key: 'rules', label: 'Правила', type: 'textarea', rows: 8, description: labels.rules },
  { key: 'safety', label: 'Безопасность', type: 'textarea', rows: 4, description: labels.safety },
  { key: 'output_requirements', label: 'Требования к выходу', type: 'textarea', rows: 4, description: labels.output },
  { key: 'model', label: 'Модель', type: 'select', options: modelOptions, description: labels.model },
  { key: 'temperature', label: 'Temperature', type: 'number' },
  { key: 'max_tokens', label: 'Макс. токенов', type: 'number' },
  { key: 'timeout_s', label: 'Таймаут (сек)', type: 'number' },
  { key: 'max_retries', label: 'Макс. попыток', type: 'number' },
  { key: 'retry_backoff', label: 'Стратегия backoff', type: 'select', options: BACKOFF_OPTIONS },
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
    max_tokens: role?.max_tokens ?? DEFAULT_ROLE_FORM.max_tokens,
    timeout_s: role?.timeout_s ?? DEFAULT_ROLE_FORM.timeout_s,
    max_retries: role?.max_retries ?? DEFAULT_ROLE_FORM.max_retries,
    retry_backoff: role?.retry_backoff ?? DEFAULT_ROLE_FORM.retry_backoff,
  };
}

export function OrchestrationPage() {
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingUpdates, setPendingUpdates] = useState<Record<string, unknown> | null>(null);
  const [executorMode, setExecutorMode] = useState<'view' | 'edit'>('view');
  const [executorForm, setExecutorForm] = useState<Record<string, unknown>>({});

  const [plannerMode, setPlannerMode] = useState<'view' | 'edit'>('view');
  const [plannerForm, setPlannerForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [synthMode, setSynthMode] = useState<'view' | 'edit'>('view');
  const [synthForm, setSynthForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [factMode, setFactMode] = useState<'view' | 'edit'>('view');
  const [factForm, setFactForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);
  const [compactMode, setCompactMode] = useState<'view' | 'edit'>('view');
  const [compactForm, setCompactForm] = useState<RoleFormData>(DEFAULT_ROLE_FORM);

  const { data: orchestrationSettings, isLoading: settingsLoading } = useOrchestrationSettings();
  const updateSettings = useUpdateOrchestrationSettings();

  const { data: plannerRole, isLoading: plannerLoading } = useActivePlannerRole();
  const { data: synthesizerRole, isLoading: synthesizerLoading } = useActiveSynthesizerRole();
  const { data: factExtractorRole, isLoading: factExtractorLoading } = useActiveFactExtractorRole();
  const { data: summaryCompactorRole, isLoading: summaryCompactorLoading } = useActiveSummaryCompactorRole();

  const updatePlannerRole = useUpdatePlannerRole();
  const updateSynthesizerRole = useUpdateSynthesizerRole();
  const updateFactExtractorRole = useUpdateFactExtractorRole();
  const updateSummaryCompactorRole = useUpdateSummaryCompactorRole();

  const { data: modelsData, isLoading: modelsLoading } = useModels({ type: 'llm_chat', enabled_only: true });

  const modelOptions = useMemo(
    () => (modelsData?.items ?? []).map((model: Model) => ({ value: model.alias, label: `${model.name} (${model.alias})` })),
    [modelsData]
  );

  const resolvedExecutorFields = useMemo(() => executorFields(modelOptions), [modelOptions]);
  const resolvedPlannerFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль planner-агента в процессе выполнения.',
    mission: 'Главная цель планировщика на каждом шаге.',
    rules: 'Логика переходов между фазами и выбора действий.',
    safety: 'Ограничения и контроль риска для планирования.',
    output: 'Строгий формат JSON-плана (goal + steps).',
    model: 'LLM-модель planner.',
  }), [modelOptions]);
  const resolvedSynthesizerFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль синтезатора итогового ответа.',
    mission: 'Сборка финального ответа пользователя из фактов рантайма.',
    rules: 'Правила формирования ответа и опоры на факты.',
    safety: 'Ограничения на чувствительные данные в финальном ответе.',
    output: 'Формат финального ответа пользователю.',
    model: 'LLM-модель synthesizer.',
  }), [modelOptions]);
  const resolvedFactExtractorFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль экстрактора фактов.',
    mission: 'Извлечение атомарных фактов из диалога.',
    rules: 'Правила отбора и нормализации фактов.',
    safety: 'Что запрещено сохранять в фактах.',
    output: 'Формат JSON-массива фактов.',
    model: 'LLM-модель fact extractor.',
  }), [modelOptions]);
  const resolvedSummaryCompactorFields = useMemo(() => roleFields(modelOptions, {
    identity: 'Роль компактора rolling summary.',
    mission: 'Обновление структурного summary диалога.',
    rules: 'Правила обновления goals/done/entities/open_questions.',
    safety: 'Ограничения на чувствительные данные в summary.',
    output: 'Формат JSON-структуры summary.',
    model: 'LLM-модель summary compactor.',
  }), [modelOptions]);

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
          actions={executorMode === 'view'
            ? [<Button key="edit" onClick={() => { setExecutorForm({ ...(orchestrationSettings ?? {}) }); setExecutorMode('edit'); }}>Редактировать</Button>]
            : [
                <Button key="save" onClick={() => { setPendingUpdates(executorForm); setShowConfirmDialog(true); }} disabled={updateSettings.isPending}>{updateSettings.isPending ? 'Сохранение...' : 'Сохранить'}</Button>,
                <Button key="cancel" variant="outline" onClick={() => { setExecutorForm({}); setExecutorMode('view'); }}>Отмена</Button>,
              ]}
        >
          <Block
            title="Модель исполнителя"
            fields={resolvedExecutorFields}
            data={executorMode === 'edit' ? executorForm : (orchestrationSettings || {})}
            editable={executorMode === 'edit'}
            onChange={executorMode === 'edit' ? (key, value) => setExecutorForm((prev) => ({ ...prev, [key]: value })) : undefined}
          />
        </Tab>

        <Tab
          title="Planner"
          layout="grid"
          actions={plannerMode === 'view'
            ? [<Button key="edit" onClick={() => { setPlannerForm(mapRoleToFields(plannerRole)); setPlannerMode('edit'); }}>Редактировать</Button>]
            : [
                <Button key="save" onClick={() => { updatePlannerRole.mutate(plannerForm); setPlannerMode('view'); }} disabled={updatePlannerRole.isPending}>{updatePlannerRole.isPending ? 'Сохранение...' : 'Сохранить'}</Button>,
                <Button key="cancel" variant="outline" onClick={() => { setPlannerMode('view'); setPlannerForm(DEFAULT_ROLE_FORM); }}>Отмена</Button>,
              ]}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedPlannerFields.filter((f) => ROLE_PROMPT_KEYS.includes(f.key))} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedPlannerFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={plannerMode === 'edit' ? plannerForm : mapRoleToFields(plannerRole)} editable={plannerMode === 'edit'} onChange={plannerMode === 'edit' ? (k, v) => setPlannerForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Synthesizer"
          layout="grid"
          actions={synthMode === 'view'
            ? [<Button key="edit" onClick={() => { setSynthForm(mapRoleToFields(synthesizerRole)); setSynthMode('edit'); }}>Редактировать</Button>]
            : [
                <Button key="save" onClick={() => { updateSynthesizerRole.mutate(synthForm); setSynthMode('view'); }} disabled={updateSynthesizerRole.isPending}>{updateSynthesizerRole.isPending ? 'Сохранение...' : 'Сохранить'}</Button>,
                <Button key="cancel" variant="outline" onClick={() => { setSynthMode('view'); setSynthForm(DEFAULT_ROLE_FORM); }}>Отмена</Button>,
              ]}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedSynthesizerFields.filter((f) => ROLE_PROMPT_KEYS.includes(f.key))} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedSynthesizerFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={synthMode === 'edit' ? synthForm : mapRoleToFields(synthesizerRole)} editable={synthMode === 'edit'} onChange={synthMode === 'edit' ? (k, v) => setSynthForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Fact Extractor"
          layout="grid"
          actions={factMode === 'view'
            ? [<Button key="edit" onClick={() => { setFactForm(mapRoleToFields(factExtractorRole)); setFactMode('edit'); }}>Редактировать</Button>]
            : [
                <Button key="save" onClick={() => { updateFactExtractorRole.mutate(factForm); setFactMode('view'); }} disabled={updateFactExtractorRole.isPending}>{updateFactExtractorRole.isPending ? 'Сохранение...' : 'Сохранить'}</Button>,
                <Button key="cancel" variant="outline" onClick={() => { setFactMode('view'); setFactForm(DEFAULT_ROLE_FORM); }}>Отмена</Button>,
              ]}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedFactExtractorFields.filter((f) => ROLE_PROMPT_KEYS.includes(f.key))} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedFactExtractorFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={factMode === 'edit' ? factForm : mapRoleToFields(factExtractorRole)} editable={factMode === 'edit'} onChange={factMode === 'edit' ? (k, v) => setFactForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>

        <Tab
          title="Summary Compactor"
          layout="grid"
          actions={compactMode === 'view'
            ? [<Button key="edit" onClick={() => { setCompactForm(mapRoleToFields(summaryCompactorRole)); setCompactMode('edit'); }}>Редактировать</Button>]
            : [
                <Button key="save" onClick={() => { updateSummaryCompactorRole.mutate(compactForm); setCompactMode('view'); }} disabled={updateSummaryCompactorRole.isPending}>{updateSummaryCompactorRole.isPending ? 'Сохранение...' : 'Сохранить'}</Button>,
                <Button key="cancel" variant="outline" onClick={() => { setCompactMode('view'); setCompactForm(DEFAULT_ROLE_FORM); }}>Отмена</Button>,
              ]}
        >
          <Block title="Правила" icon="shield" iconVariant="primary" width="2/3" fields={resolvedSummaryCompactorFields.filter((f) => ROLE_PROMPT_KEYS.includes(f.key))} data={compactMode === 'edit' ? compactForm : mapRoleToFields(summaryCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
          <Block title="Параметры" icon="settings" iconVariant="info" width="1/3" fields={resolvedSummaryCompactorFields.filter((f) => ROLE_PARAM_KEYS.includes(f.key))} data={compactMode === 'edit' ? compactForm : mapRoleToFields(summaryCompactorRole)} editable={compactMode === 'edit'} onChange={compactMode === 'edit' ? (k, v) => setCompactForm((p) => ({ ...p, [k]: v })) : undefined} />
        </Tab>
      </EntityPageV2>

      {(settingsLoading || modelsLoading || plannerLoading || synthesizerLoading || factExtractorLoading || summaryCompactorLoading) && (
        <div>Загрузка настроек оркестрации…</div>
      )}

      <ConfirmDialog
        open={showConfirmDialog}
        title="Подтвердите сохранение"
        message="Вы уверены, что хотите сохранить изменения в настройках оркестрации? Это повлияет на всех агентов и процессы выполнения."
        confirmLabel="Сохранить"
        cancelLabel="Отмена"
        variant="danger"
        onConfirm={() => {
          if (pendingUpdates) {
            updateSettings.mutate(pendingUpdates, {
              onSuccess: () => {
                setShowConfirmDialog(false);
                setPendingUpdates(null);
                setExecutorMode('view');
              },
            });
          }
        }}
        onCancel={() => {
          setShowConfirmDialog(false);
          setPendingUpdates(null);
        }}
      />
    </>
  );
}

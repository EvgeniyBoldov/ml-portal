import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { Badge, DataTable, EntityPageV2, Tab, type DataTableColumn } from '@/shared/ui';
import { adminApi, type SemanticMemoryAdminDetail } from '@/shared/api/admin';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';

const labelFor = (key: string): string => ({
  summary: 'Краткое описание', details: 'Детали', statement: 'Формулировка', effect: 'Эффект',
  conditions: 'Условия', required_approvals: 'Необходимые согласования', required_checks: 'Проверки',
  exceptions: 'Исключения', consequences: 'Последствия', limits: 'Ограничения', decision: 'Решение',
  rationale: 'Обоснование', goal: 'Цель', applicability_conditions: 'Условия применимости',
  prechecks: 'Предварительные проверки', verification: 'Верификация', rollback: 'Откат',
})[key] ?? key.split('_').join(' ');

const contentFields = (content: Record<string, unknown>): FieldConfig[] => Object.entries(content)
  .filter(([key]) => key !== 'steps')
  .map(([key, value]) => {
    const isDate = typeof value === 'string' && /(date|_at|timestamp)$/i.test(key);
    const type: FieldConfig['type'] = Array.isArray(value) ? 'tags' : isDate ? 'date' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : typeof value === 'object' && value !== null ? 'json' : 'textarea';
    return { key, label: labelFor(key), type, editable: false };
  });

const sourceColumns: DataTableColumn<SemanticMemoryAdminDetail['sources'][number]>[] = [
  { key: 'document_id', label: 'ДОКУМЕНТ', render: (row) => row.document_id },
  { key: 'section_id', label: 'SECTION', width: 180 },
  { key: 'label', label: 'МЕТКА', render: (row) => row.label || '—' },
  { key: 'start_offset', label: 'НАЧАЛО', width: 100, align: 'right', render: (row) => row.start_offset ?? '—' },
  { key: 'end_offset', label: 'КОНЕЦ', width: 100, align: 'right', render: (row) => row.end_offset ?? '—' },
];

const relationColumns: DataTableColumn<SemanticMemoryAdminDetail['relations'][number]>[] = [
  { key: 'relation_type', label: 'СВЯЗЬ' },
  { key: 'target_type', label: 'ТИП ЦЕЛИ' },
  { key: 'target_id', label: 'ЦЕЛЬ' },
];

const claimColumns: DataTableColumn<SemanticMemoryAdminDetail['claims'][number]>[] = [
  { key: 'document_id', label: 'ДОКУМЕНТ', render: (row) => row.document_id },
  { key: 'scope_keys', label: 'СКОУПЫ', render: (row) => row.scope_keys.length ? row.scope_keys.join(', ') : row.scope },
  { key: 'state', label: 'СОСТОЯНИЕ' },
  { key: 'confidence', label: 'УВЕРЕННОСТЬ', render: (row) => `${Math.round(row.confidence * 100)}%` },
];

function ProcedureSteps({ steps }: { steps: unknown }) {
  if (!Array.isArray(steps) || !steps.length) return <span>Шаги не указаны</span>;
  const rows = steps.map((step, index) => {
    const value = step && typeof step === 'object' ? step as Record<string, unknown> : {};
    return { id: String(index), order: Number(value.order ?? index + 1), instruction: String(value.instruction ?? ''), expected_result: String(value.expected_result ?? ''), confirmation_required: Boolean(value.confirmation_required) };
  });
  const columns: DataTableColumn<typeof rows[number]>[] = [
    { key: 'order', label: '№', width: 60, align: 'right' },
    { key: 'instruction', label: 'ИНСТРУКЦИЯ' },
    { key: 'expected_result', label: 'ОЖИДАЕМЫЙ РЕЗУЛЬТАТ' },
    { key: 'confirmation_required', label: 'ПОДТВЕРЖДЕНИЕ', width: 150, render: (row) => <Badge tone={row.confirmation_required ? 'warn' : 'neutral'}>{row.confirmation_required ? 'Требуется' : 'Нет'}</Badge> },
  ];
  return <DataTable columns={columns} data={rows} keyField="id" emptyText="Шаги не указаны" />;
}

export default function MemoryItemPage() {
  const { itemId } = useParams<{ itemId: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'memory', itemId],
    queryFn: () => adminApi.getSemanticMemoryItem(itemId || ''),
    enabled: Boolean(itemId),
  });
  const fields = useMemo(() => contentFields(data?.content ?? {}), [data?.content]);
  if (isError) return <EntityPageV2 title="MemoryItem" mode="view"><Tab title="Ошибка" layout="full"><p role="alert">Не удалось загрузить MemoryItem.</p></Tab></EntityPageV2>;
  if (isLoading || !data) return <EntityPageV2 title="MemoryItem" mode="view"><Tab title="Загрузка" layout="full"><p>Загрузка…</p></Tab></EntityPageV2>;

  return <EntityPageV2 title={data.subject} mode="view" breadcrumbs={[{ label: 'Мемори', href: '/admin/memory' }, { label: data.subject }]}>
    <Tab title="Обзор" id="overview" layout="grid">
      <Block title="Основная информация" icon="database" iconVariant="info" width="1/2" fields={[
        { key: 'scope', label: 'Область', type: 'badge', badgeTone: 'info', editable: false },
        { key: 'item_type', label: 'Тип знания', type: 'badge', editable: false },
        { key: 'subject', label: 'Тема', type: 'text', editable: false },
        { key: 'project_id', label: 'Проект', type: 'code', editable: false },
      ]} data={data} />
      <Block title="Состояние и уверенность" icon="activity" iconVariant="success" width="1/2" fields={[
        { key: 'state', label: 'Состояние', type: 'badge', badgeTone: data.state === 'active' ? 'success' : data.state === 'uncertain' ? 'warn' : 'danger', editable: false },
        { key: 'confidence', label: 'Уверенность', type: 'number', editable: false },
        { key: 'source_count', label: 'Источники', type: 'number', editable: false },
        { key: 'claim_count', label: 'Claims', type: 'number', editable: false },
        { key: 'last_verified_at', label: 'Последняя проверка', type: 'date', editable: false },
        { key: 'updated_at', label: 'Обновлён', type: 'date', editable: false },
      ]} data={data} />
      <Block title="Применимость и видимость" icon="shield" iconVariant="warning" width="full" fields={[
        { key: 'applicability', label: 'Применимость', type: 'json', editable: false },
        { key: 'visibility', label: 'Видимость', type: 'json', editable: false },
      ]} data={data} />
    </Tab>
    <Tab title="Содержимое" id="content" layout="grid">
      <Block title="Типизированное содержимое" icon="file-text" iconVariant="primary" width="full" fields={fields} data={data.content} />
      {data.item_type === 'procedure' && <Block title="Шаги процедуры" icon="list" iconVariant="info" width="full"><ProcedureSteps steps={data.content.steps} /></Block>}
    </Tab>
    <Tab title="Происхождение" id="provenance" layout="full">
      <Block title="Утверждения и скоупы" icon="database" iconVariant="info"><DataTable columns={claimColumns} data={data.claims} keyField="id" emptyText="Утверждений нет" /></Block>
      <Block title="Источники" icon="file" iconVariant="info"><DataTable columns={sourceColumns} data={data.sources} keyField="section_id" emptyText="Источники не найдены" /></Block>
      <Block title="Связи" icon="link" iconVariant="primary"><DataTable columns={relationColumns} data={data.relations.map((row, index) => ({ ...row, id: `${row.relation_type}:${row.target_type}:${row.target_id}:${index}` }))} keyField="id" emptyText="Связи не найдены" /></Block>
    </Tab>
  </EntityPageV2>;
}

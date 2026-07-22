import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorTextBlock } from '@/shared/ui/Inspector';

const present = (value: unknown): boolean => value !== null && value !== undefined && value !== '';
const record = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
);

export function PlanView({ plan }: { plan: unknown }) {
  const value = record(plan);
  const patch = value.patch ?? value.plan ?? value.effective_plan ?? plan;
  const tasks = Array.isArray(value.tasks) ? value.tasks : undefined;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Ревизия">{present(value.revision) ? String(value.revision) : '—'}</InspectorFieldRow>
    <InspectorFieldRow label="Режим">{String(value.mode ?? value.trigger ?? '—')}</InspectorFieldRow>
    <InspectorFieldRow label="Причина">{String(value.reason ?? value.trigger ?? '—')}</InspectorFieldRow>
    {tasks ? <InspectorFieldRow label="Задач">{String(tasks.length)}</InspectorFieldRow> : null}
    <InspectorFieldRow label="План"><InspectorJsonBlock value={patch ?? '—'} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function LimitsView({ snapshot }: { snapshot: unknown }) {
  const value = record(snapshot);
  const limits = record(value.limits ?? value.runtime_limits ?? value);
  return <InspectorFieldGroup>
    {Object.keys(limits).length === 0 ? <InspectorFieldRow label="Лимиты">—</InspectorFieldRow> : <InspectorJsonBlock value={limits} />}
  </InspectorFieldGroup>;
}

export function RbacView({ snapshot }: { snapshot: unknown }) {
  const value = record(snapshot);
  const rbac = record(value.rbac ?? value);
  return <InspectorFieldGroup>
    {Object.keys(rbac).length === 0 ? <InspectorFieldRow label="RBAC">—</InspectorFieldRow> : <InspectorJsonBlock value={rbac} />}
  </InspectorFieldGroup>;
}

export function TextValue({ label, value }: { label: string; value: unknown }) {
  const text = typeof value === 'string' ? value : value === null || value === undefined ? '—' : JSON.stringify(value, null, 2);
  return <InspectorFieldRow label={label}><InspectorTextBlock text={text} /></InspectorFieldRow>;
}

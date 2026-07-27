import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar } from '@/shared/ui/Inspector';
import { HumanPlanView } from './PlanView';

const record = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
);

export function PlanView({ plan }: { plan: unknown }) {
  return <HumanPlanView plan={plan} />;
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
  if (value === null || value === undefined || ['string', 'number', 'boolean'].includes(typeof value)) {
    return <InspectorFieldRow label={label}><InspectorScalar value={value as string | number | boolean | null | undefined} /></InspectorFieldRow>;
  }
  return <InspectorFieldRow label={label}><InspectorJsonBlock value={value} /></InspectorFieldRow>;
}

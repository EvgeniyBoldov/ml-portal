import { InspectorFieldRow, InspectorJsonBlock, InspectorScalar } from '@/shared/ui/Inspector';
import { HumanPlanView } from './PlanView';
import type { PlanViewModel } from '../../planInspection';

export function PlanView({ plan }: { plan?: PlanViewModel }) {
  return <HumanPlanView plan={plan} />;
}

export function TextValue({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || ['string', 'number', 'boolean'].includes(typeof value)) {
    return <InspectorFieldRow label={label}><InspectorScalar value={value as string | number | boolean | null | undefined} /></InspectorFieldRow>;
  }
  return <InspectorFieldRow label={label}><InspectorJsonBlock value={value} /></InspectorFieldRow>;
}

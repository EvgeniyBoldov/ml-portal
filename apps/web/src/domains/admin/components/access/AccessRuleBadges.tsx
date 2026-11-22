import type { EnrichedRule, RbacEffect } from '@/shared/api/rbac';
import { Badge } from '@/shared/ui';
import {
  RBAC_EFFECT_LABELS,
  RBAC_EFFECT_TONES,
} from '@/domains/admin/shared/rbacLabels';
import { statusName } from './accessRules';

export function AccessDecisionBadge({ effect }: { effect: RbacEffect }) {
  return (
    <Badge tone={RBAC_EFFECT_TONES[effect]}>{RBAC_EFFECT_LABELS[effect]}</Badge>
  );
}

export function AccessStatusBadge({ rule }: { rule: EnrichedRule }) {
  return (
    <Badge tone={rule.lifecycle_status === 'deprecated' ? 'warn' : 'neutral'}>
      {statusName(rule)}
    </Badge>
  );
}

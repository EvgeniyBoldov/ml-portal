import type { BudgetState } from '../aggregator';
import styles from './TraceV2.module.css';

interface Props {
  budget: BudgetState;
}

function pct(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.round((used / limit) * 100);
}

export function BudgetBadge({ budget }: Props) {
  const stepsPct = pct(budget.steps.used, budget.steps.limit);
  const toolsPct = pct(budget.tools.used, budget.tools.limit);
  const maxPct = Math.max(stepsPct, toolsPct);

  const cls = maxPct >= 90
    ? styles.budgetBadgeDanger
    : maxPct >= 70
      ? styles.budgetBadgeWarn
      : '';

  const parts: string[] = [];

  if (budget.steps.limit > 0) {
    parts.push(`steps ${budget.steps.used}/${budget.steps.limit}`);
  }
  if (budget.tools.limit > 0) {
    parts.push(`tools ${budget.tools.used}/${budget.tools.limit}`);
  }
  if (budget.retries.limit > 0 && budget.retries.used > 0) {
    parts.push(`↻${budget.retries.used}`);
  }
  if (budget.tokens && budget.tokens.used > 0) {
    const limit = budget.tokens.limit;
    parts.push(limit ? `tok ${budget.tokens.used}/${limit}` : `tok ${budget.tokens.used}`);
  }

  if (parts.length === 0) return null;

  return (
    <span className={`${styles.budgetBadge} ${cls}`}>
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && <span className={styles.budgetSep}> | </span>}
          {p}
        </span>
      ))}
    </span>
  );
}

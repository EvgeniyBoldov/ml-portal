import Badge from '@/shared/ui/Badge';
import {
  InspectorDate,
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorNotice,
  InspectorScalar,
} from '@/shared/ui/Inspector';
import type { SandboxBranchFactsArtifact } from '../types';
import styles from './BranchFactsInspector.module.css';

type FactRecord = Record<string, unknown>;
type FactScope = 'user' | 'tenant' | 'project';

const SCOPES: FactScope[] = ['user', 'tenant', 'project'];

function asRecords(value: unknown): FactRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is FactRecord => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : [];
}

function asRecord(value: unknown): FactRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as FactRecord : null;
}

function asText(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '—';
}

function countFacts(artifact: SandboxBranchFactsArtifact, key: 'base' | 'effective'): number {
  return SCOPES.reduce((total, scope) => total + asRecords(artifact[key]?.[scope]).length, 0);
}

function countOverrides(artifact: SandboxBranchFactsArtifact): number {
  return SCOPES.reduce((total, scope) => total + Object.keys(artifact.overrides?.[scope] ?? {}).length, 0);
}

function stateTone(state: string): 'success' | 'warn' | 'neutral' {
  if (state === 'set') return 'success';
  if (state === 'deleted') return 'warn';
  return 'neutral';
}

function FactRow({ fact, override }: { fact: FactRecord; override?: FactRecord | null }) {
  const state = typeof override?.state === 'string' ? override.state : '';
  const isOverridden = state === 'set';
  return (
    <div className={styles.row}>
      <div className={styles.main}>
        <span className={styles.subject}>{asText(fact.subject)}</span>
        <span className={styles.value}>{asText(fact.value)}</span>
      </div>
      <div className={styles.meta}>
        <Badge size="small" tone={isOverridden ? 'success' : 'neutral'}>{isOverridden ? 'Override' : 'База'}</Badge>
        {fact.status ? <Badge size="small" tone={fact.status === 'confirmed' ? 'success' : 'warn'}>{asText(fact.status)}</Badge> : null}
        {fact.source ? <span>{asText(fact.source)}</span> : null}
        {typeof fact.confidence === 'number' ? <span>{Math.round(fact.confidence * 100)}%</span> : null}
      </div>
    </div>
  );
}

export function BranchFactsInspector({
  artifact,
  isLoading,
  isError,
}: {
  artifact?: SandboxBranchFactsArtifact;
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) return <InspectorNotice tone="neutral" message="Загружаю факты ветки…" />;
  if (isError || !artifact) return <InspectorNotice tone="warn" message="Не удалось загрузить факты ветки." />;

  const deleted = SCOPES.flatMap((scope) =>
    Object.entries(artifact.overrides?.[scope] ?? {})
      .filter(([, value]) => asRecord(value)?.state === 'deleted')
      .map(([subject, value]) => ({ scope, subject, override: asRecord(value)! })),
  );
  const effectiveCount = countFacts(artifact, 'effective');

  return (
    <div className={styles.inspector}>
      <InspectorFieldGroup>
        <InspectorFieldRow label="Фактов в базе"><InspectorScalar value={countFacts(artifact, 'base')} /></InspectorFieldRow>
        <InspectorFieldRow label="Изменений ветки"><InspectorScalar value={countOverrides(artifact)} /></InspectorFieldRow>
        <InspectorFieldRow label="Эффективных фактов"><InspectorScalar value={effectiveCount} /></InspectorFieldRow>
        <InspectorFieldRow label="Обновлено"><InspectorDate value={artifact.updated_at} /></InspectorFieldRow>
      </InspectorFieldGroup>

      {effectiveCount === 0 ? <InspectorNotice tone="neutral" message="В этой ветке пока нет эффективных фактов." /> : null}

      {SCOPES.map((scope) => {
        const facts = asRecords(artifact.effective?.[scope]);
        if (!facts.length) return null;
        const overrides = artifact.overrides?.[scope] ?? {};
        return (
          <section className={styles.section} key={scope}>
            <div className={styles.sectionTitle}>
              <span>{scope}</span>
              <Badge size="small" tone="neutral">{facts.length}</Badge>
            </div>
            <div className={styles.rows}>
              {facts.map((fact, index) => {
                const subject = typeof fact.subject === 'string' ? fact.subject : '';
                return <FactRow key={`${scope}:${subject}:${index}`} fact={fact} override={asRecord(overrides[subject])} />;
              })}
            </div>
          </section>
        );
      })}

      {deleted.length ? (
        <section className={styles.section}>
          <div className={styles.sectionTitle}>
            <span>Скрыто в ветке</span>
            <Badge size="small" tone="warn">{deleted.length}</Badge>
          </div>
          <div className={styles.rows}>
            {deleted.map(({ scope, subject, override }) => (
              <div className={styles.row} key={`${scope}:${subject}`}>
                <div className={styles.main}>
                  <span className={styles.subject}>{subject}</span>
                  <span className={styles.value}>{scope}</span>
                </div>
                <div className={styles.meta}><Badge size="small" tone={stateTone(asText(override.state))}>Удалён</Badge></div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

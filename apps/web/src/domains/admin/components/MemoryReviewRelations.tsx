import { Badge } from '@/shared/ui';
import type { MemoryScopeAdminItem, ShadowMemoryCandidate } from '@/shared/api/admin';
import { scopeLabels } from './MemoryReviewTable';
import { scopeStatusLabels, scopeTypeLabels } from './MemoryScopeTable';
import styles from './MemoryReviewDialog.module.css';

const bindingLabels: Record<string, string> = { suggested: 'Предложена', confirmed: 'Подтверждена', rejected: 'Отклонена', active: 'Активна', resolved: 'Утверждена', needs_review: 'На проверке', extracted: 'Извлечена' };

export default function MemoryReviewRelations({ candidate, scopes }: { candidate: ShadowMemoryCandidate; scopes: MemoryScopeAdminItem[] }) {
  const scopeName = (key: string) => scopes.find((scope) => scope.key === key)?.name || key;
  return <div className={styles.panel}>
    <section className={styles.section}>
      <h3>Область действия</h3>
      <Badge tone={candidate.candidate_type === 'term' || candidate.scope_candidate !== 'unknown' && Boolean(candidate.scope_candidate) ? 'info' : 'warn'}>
        {candidate.candidate_type === 'term' ? 'Общий глоссарий' : scopeLabels[candidate.scope_candidate || 'unknown'] ?? candidate.scope_candidate}
      </Badge>
      {candidate.candidate_type !== 'term' && (!candidate.scope_candidate || candidate.scope_candidate === 'unknown') && <p>Выберите область тегами выше и сохраните применимость. После этого статус кандидата обновится.</p>}
      {candidate.scope_rationale && <div><h4>Обоснование применимости</h4><p>{candidate.scope_rationale}</p></div>}
      {candidate.scope_keys.length > 0 && <div><h4>Области применимости</h4><ul>{candidate.scope_keys.map((key) => <li key={key} title={key}>{scopeName(key)}</li>)}</ul></div>}
      {candidate.related_project_keys.length > 0 && <div><h4>Связанные проекты</h4><ul>{candidate.related_project_keys.map((key) => <li key={key}>{key}</li>)}</ul></div>}
    </section>
    <section className={styles.section}>
      <h3>Предложения областей</h3>
      {!candidate.scope_proposals.length && <p>Предложений новых областей нет.</p>}
      {candidate.scope_proposals.map((item) => <div key={item.id} className={styles.relationCard}>
        <div className={styles.eyebrow}><Badge tone={item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'warn'}>{scopeStatusLabels[item.status] ?? item.status}</Badge><span>{scopeTypeLabels[item.scope_type] ?? item.scope_type}</span></div>
        <strong>{item.name}</strong>
        <p>{item.role === 'applies_to' ? 'Знание применяется к этой области' : 'Область упомянута в знании'}</p>
        {item.term_name && <p>Термин: {item.term_name}</p>}
        {item.rejection_reason && <p>Причина отклонения: {item.rejection_reason}</p>}
      </div>)}
      {candidate.scope_proposals.some((item) => item.status === 'needs_review' || item.status === 'awaiting_term') && <p>Предложения проверяются на вкладке «Скоупы» страницы памяти. Сначала утвердите связанный термин, затем область.</p>}
    </section>
    <section className={styles.section}>
      <h3>Связанные термины</h3>
      {candidate.related_terms.length ? candidate.related_terms.map((item) => <div className={styles.relationCard} key={`${item.term}:${item.scope}`}><strong>{item.term}</strong>{item.scope && <p>Область: {item.scope}</p>}<Badge tone="neutral">{bindingLabels[item.status] ?? item.status}</Badge></div>) : <p>Связей с терминами нет.</p>}
    </section>
    {(candidate.mentioned_scope_keys.length > 0 || candidate.unmatched_scope_names.length > 0 || candidate.related_entities.length > 0) && <section className={styles.section}>
      <h3>Упоминания и несопоставленные связи</h3>
      {candidate.mentioned_scope_keys.length > 0 && <div><h4>Упомянутые области</h4><p>Упоминание не подтверждает применимость знания.</p><ul>{candidate.mentioned_scope_keys.map((key) => <li key={key} title={key}>{scopeName(key)}</li>)}</ul></div>}
      {candidate.unmatched_scope_names.length > 0 && <div><h4>Не удалось сопоставить с каталогом</h4><ul>{candidate.unmatched_scope_names.map((name) => <li key={name}>{name}</li>)}</ul></div>}
      {candidate.related_entities.some((entity) => entity.type !== 'glossary_term') && <div><h4>Связанные сущности</h4>{candidate.related_entities.filter((entity) => entity.type !== 'glossary_term').map((entity, index) => <p key={index}>{Object.entries(entity).map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`).join(' · ')}</p>)}</div>}
    </section>}
  </div>;
}

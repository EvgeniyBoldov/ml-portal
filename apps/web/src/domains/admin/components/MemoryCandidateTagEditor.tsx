import { Button } from '@/shared/ui';
import type { PublishedMemoryTerm, MemoryCandidateTags, MemoryScopeAdminItem, ShadowMemoryCandidate } from '@/shared/api/admin';
import MemoryTagPicker from './MemoryTagPicker';
import styles from './MemoryReviewDialog.module.css';

type Props = {
  candidate: ShadowMemoryCandidate; scopes: MemoryScopeAdminItem[]; terms: PublishedMemoryTerm[];
  value: MemoryCandidateTags; onChange: (draft: MemoryCandidateTags) => void;
  pending: boolean; onRefreshCatalogs: () => void;
};
const fields = [{ type: 'project', label: 'Проекты' }, { type: 'team', label: 'Команды' }, { type: 'product', label: 'Продукты' }];

export default function MemoryCandidateTagEditor({ candidate, scopes, terms, value, onChange, pending, onRefreshCatalogs }: Props) {
  const activeScopes = scopes.filter((scope) => scope.lifecycle_status === 'active');
  const handleScopesChange = (type: string, ids: string[]) => {
    const added = ids.find((id) => !value.scope_ids.includes(id));
    const addedScope = activeScopes.find((scope) => scope.id === added);
    const selected = ids.filter((id) => {
      const scope = activeScopes.find((item) => item.id === id);
      return !addedScope || id === added || !scope || !scope.is_all && !addedScope.is_all;
    });
    onChange({ ...value, company_wide: false, scope_ids: [
      ...value.scope_ids.filter((id) => activeScopes.find((scope) => scope.id === id)?.scope_type !== type), ...selected,
    ] });
  };
  return <section className={styles.section}>
    {candidate.candidate_type !== 'term' && fields.map(({ type, label }) => {
      const options = activeScopes.filter((scope) => scope.scope_type === type);
      return <MemoryTagPicker key={type} label={label}
        options={options.map((scope) => ({ value: scope.id, label: scope.name, search: `${scope.key} ${scope.aliases.join(' ')}` }))}
        value={value.scope_ids.filter((id) => options.some((scope) => scope.id === id))}
        disabled={pending} onChange={(ids) => handleScopesChange(type, ids)} />;
    })}
    <MemoryTagPicker label="Термины" options={terms.map((term) => ({ value: term.id, label: term.canonical_term, search: `${term.aliases.join(' ')} ${term.definition}` }))}
      value={value.glossary_term_ids} disabled={pending} onChange={(ids) => onChange({ ...value, company_wide: false, glossary_term_ids: ids })} />
    <Button size="sm" variant="outline" disabled={pending} onClick={onRefreshCatalogs}>Обновить списки</Button>
  </section>;
}

import { useState } from 'react';
import { Badge, Button, Input, Modal } from '@/shared/ui';
import type { MemoryScopeAdminItem, ShadowMemoryCandidate } from '@/shared/api/admin';

export type MemoryApproval = {
  scope: 'global' | 'project' | 'scoped';
  project_id?: string;
  scope_ids?: string[];
};

type Props = {
  candidate: ShadowMemoryCandidate;
  scopes: MemoryScopeAdminItem[];
  pending: boolean;
  onClose: () => void;
  onApprove: (decision: MemoryApproval) => Promise<void>;
};

const scopeTypes = ['product', 'project', 'team'] as const;

export default function MemoryReviewDialog({ candidate, scopes, pending, onClose, onApprove }: Props) {
  const suggestedMode = candidate.scope_candidate;
  const [mode, setMode] = useState<'' | MemoryApproval['scope']>(
    suggestedMode === 'global' || suggestedMode === 'project' || suggestedMode === 'scoped' ? suggestedMode : '',
  );
  const [projectId, setProjectId] = useState(candidate.project_ids.length === 1 ? candidate.project_ids[0] : '');
  const [scopeIds, setScopeIds] = useState<string[]>(candidate.scope_ids);
  const [scopeFilter, setScopeFilter] = useState('');
  const [error, setError] = useState('');
  const activeScopes = scopes.filter((scope) => scope.lifecycle_status === 'active');
  const needle = scopeFilter.trim().toLocaleLowerCase();

  const toggleScope = (scope: MemoryScopeAdminItem) => {
    if (scopeIds.includes(scope.id)) {
      setScopeIds(scopeIds.filter((id) => id !== scope.id));
      return;
    }
    const sameType = new Set(activeScopes.filter((entry) => entry.scope_type === scope.scope_type &&
      (entry.is_all || scope.is_all)).map((entry) => entry.id));
    setScopeIds([...scopeIds.filter((id) => !sameType.has(id)), scope.id]);
  };

  const approve = async () => {
    setError('');
    try {
      if (mode === 'global') await onApprove({ scope: 'global' });
      if (mode === 'project') await onApprove({ scope: 'project', project_id: projectId });
      if (mode === 'scoped') await onApprove({ scope: 'scoped', scope_ids: scopeIds });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось утвердить память');
    }
  };

  return (
    <Modal open title={`Проверка памяти: ${candidate.subject}`} onClose={onClose} size="lg">
      <div style={{ display: 'grid', gap: 14 }}>
        <div><strong>{candidate.candidate_type}</strong><pre style={{ whiteSpace: 'pre-wrap', maxHeight: 140, overflow: 'auto' }}>{JSON.stringify(candidate.content, null, 2)}</pre></div>
        <div>Доказательства: {candidate.evidence_section_ids.join(', ') || '—'}</div>
        {candidate.scope_rationale && <div>Основание выбора LLM: {candidate.scope_rationale}</div>}
        {candidate.mentioned_scope_keys.length > 0 && <div>Только упомянуты: {candidate.mentioned_scope_keys.join(', ')}</div>}
        {candidate.unmatched_scope_names.length > 0 && <div><Badge tone="warn">Нет в каталоге</Badge> {candidate.unmatched_scope_names.join(', ')}. При необходимости создайте скоуп на вкладке «Скоупы».</div>}
        {candidate.conflict_ids.length > 0 && <p role="alert">У кандидата есть нерешённый конфликт. Сначала разрешите его.</p>}
        <label>Применимость
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)} style={{ display: 'block', width: '100%' }}>
            <option value="">Выберите применимость</option>
            <option value="global">Глобальная память</option>
            <option value="scoped">Типизированные скоупы</option>
            {candidate.project_ids.length > 0 && <option value="project">Проект (совместимый режим)</option>}
          </select>
        </label>
        {mode === 'project' && <label>Проект
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)} style={{ display: 'block', width: '100%' }}>
            <option value="">Выберите проект</option>
            {candidate.project_ids.map((id) => {
              const linkedScope = activeScopes.find((scope) => scope.project_id === id);
              return <option key={id} value={id}>{linkedScope?.name ?? id}</option>;
            })}
          </select>
        </label>}
        {mode === 'scoped' && <div>
          <div style={{ marginBottom: 8 }}>Скоупы применимости: внутри типа действует ИЛИ, между типами — И.</div>
          <Input aria-label="Поиск скоупа" placeholder="Поиск по названию, ключу или алиасу" value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value)} />
          <div style={{ maxHeight: 280, overflow: 'auto', marginTop: 8 }}>
            {scopeTypes.map((scopeType) => {
              const options = activeScopes.filter((scope) => scope.scope_type === scopeType &&
                (!needle || [scope.key, scope.name, ...scope.aliases].join(' ').toLocaleLowerCase().includes(needle)));
              return options.length > 0 && <div key={scopeType} style={{ marginBottom: 12 }}>
                <strong>{scopeType}</strong>
                {options.map((scope) => <label key={scope.id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 5 }}>
                  <input type="checkbox" checked={scopeIds.includes(scope.id)} onChange={() => toggleScope(scope)} />
                  {scope.name} <code>{scope.key}</code>
                </label>)}
              </div>;
            })}
          </div>
        </div>}
        {error && <p role="alert">{error}</p>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button disabled={pending || candidate.conflict_ids.length > 0 || !mode ||
            (mode === 'project' && !projectId) || (mode === 'scoped' && scopeIds.length === 0)}
            onClick={approve}>Утвердить</Button>
        </div>
      </div>
    </Modal>
  );
}

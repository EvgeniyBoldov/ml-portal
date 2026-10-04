import type { FieldConfig } from '@/shared/ui/GridLayout';
import type { MemoryCandidateTags, MemoryScopeAdminItem, PublishedMemoryTerm } from '@/shared/api/admin';
import MemoryTagPicker from './MemoryTagPicker';
import MemoryApplicabilityValue from './MemoryApplicabilityValue';

export function memoryLinksFields({ scopes, terms, value, onChange, pending }: {
  scopes: MemoryScopeAdminItem[]; terms: PublishedMemoryTerm[]; value: MemoryCandidateTags;
  onChange: (draft: MemoryCandidateTags) => void; pending: boolean;
}): FieldConfig[] {
  const activeScopes = scopes.filter((scope) => scope.lifecycle_status === 'active');
  const handleScopesChange = (type: string, ids: string[]) => {
    const added = activeScopes.find((scope) => ids.includes(scope.id) && !value.scope_ids.includes(scope.id));
    const selected = ids.filter((id) => {
      const scope = activeScopes.find((item) => item.id === id);
      return !added || id === added.id || !scope || !scope.is_all && !added.is_all;
    });
    onChange({ ...value, scope_ids: [
      ...value.scope_ids.filter((id) => activeScopes.find((scope) => scope.id === id)?.scope_type !== type), ...selected,
    ] });
  };
  const fields: FieldConfig[] = [{ type: 'project', label: 'Проекты' }, { type: 'team', label: 'Команды' }].map(({ type, label }) => {
    const options = activeScopes.filter((scope) => scope.scope_type === type);
    return { key: type, label, type: 'custom', render: (_: unknown, editable: boolean) => <MemoryTagPicker label={label} hideLabel
      options={options.map((scope) => ({ value: scope.id, label: scope.name, search: `${scope.key} ${scope.aliases.join(' ')}` }))}
      value={value.scope_ids.filter((id) => options.some((scope) => scope.id === id))}
      disabled={!editable || pending} onChange={(ids) => handleScopesChange(type, ids)} /> };
  });
  fields.push({ key: 'glossary_term_ids', label: 'Термины', type: 'custom', render: (_: unknown, editable: boolean) =>
    <MemoryTagPicker label="Термины" hideLabel
      options={terms.map((term) => ({ value: term.id, label: term.canonical_term, search: `${term.aliases.join(' ')} ${term.definition}` }))}
      value={value.glossary_term_ids} disabled={!editable || pending} onChange={(ids) => onChange({ ...value, glossary_term_ids: ids })} /> });
  return fields;
}

/** Preserve other relation types as labeled fields, omitting links already represented by a picker. */
export function otherMemoryLinksFields(entities: Array<Record<string, unknown>>, relations: Array<{ relation_type: string; target_type: string; target_id: string }>,
  selected: Set<string>): { fields: FieldConfig[]; data: Record<string, string[]> } {
  const groups = new Map<string, Map<string, string>>();
  const typeLabels: Record<string, string> = { project: 'Проекты', team: 'Команды', glossary_term: 'Термины',
    memory_item: 'Атомы памяти', system: 'Системы', service: 'Сервисы', entity: 'Сущности' };
  const add = (type: string, id: string, name: string) => {
    if (selected.has(id)) return;
    const label = typeLabels[type] ? `Другие связи — ${typeLabels[type]}` : `Связи — ${type.replace(/_/g, ' ')}`;
    const group = groups.get(label) ?? new Map<string, string>();
    if (!group.has(id)) group.set(id, name);
    groups.set(label, group);
  };
  entities.forEach((entity) => add(String(entity.type ?? 'entity'), String(entity.id ?? entity.name), String(entity.name ?? entity.id)));
  relations.forEach((relation) => add(relation.target_type, relation.target_id, relation.target_id));
  const data: Record<string, string[]> = {};
  const fields: FieldConfig[] = [];
  groups.forEach((group, label) => {
    const key = `other-${fields.length}`;
    data[key] = [...group.values()];
    fields.push({ key, label, type: 'custom', editable: false, render: (value: unknown) => <MemoryApplicabilityValue value={value} /> });
  });
  return { fields, data };
}

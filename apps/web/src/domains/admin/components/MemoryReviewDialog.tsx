import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge, Button, Input, Modal } from '@/shared/ui';
import { adminApi, type MemoryScopeAdminItem, type ShadowMemoryCandidate } from '@/shared/api/admin';
import styles from './MemoryReviewDialog.module.css';

export type MemoryApproval = {
  reason?: string;
  replace_existing_definition?: boolean;
  scope?: 'global' | 'project' | 'scoped';
  project_id?: string;
  scope_ids?: string[];
  content?: Record<string, unknown>;
};

type Props = {
  candidate: ShadowMemoryCandidate;
  scopes: MemoryScopeAdminItem[];
  pending: boolean;
  onClose: () => void;
  onApprove: (decision: MemoryApproval) => Promise<void>;
};
type Field = { key: string; label: string; required?: boolean; list?: boolean };
type Step = { instruction: string; expected_result: string; confirmation_required: boolean };

const typeLabels: Record<string, string> = {
  term: 'Термин', description: 'Описание', relationship: 'Связь', rule: 'Правило',
  constraint: 'Ограничение', procedure: 'Процедура', decision: 'Решение',
};
const fieldSets: Record<string, Field[]> = {
  term: [{ key: 'definition', label: 'Определение', required: true }],
  description: [{ key: 'summary', label: 'Краткое описание', required: true }, { key: 'details', label: 'Подробности', list: true }],
  relationship: [{ key: 'summary', label: 'Как связаны сущности', required: true }],
  rule: [{ key: 'statement', label: 'Суть правила', required: true }, { key: 'conditions', label: 'Условия', list: true },
    { key: 'required_approvals', label: 'Необходимые согласования', list: true }, { key: 'required_checks', label: 'Обязательные проверки', list: true },
    { key: 'exceptions', label: 'Исключения', list: true }, { key: 'consequences', label: 'Последствия', list: true }],
  constraint: [{ key: 'statement', label: 'Суть ограничения', required: true }, { key: 'conditions', label: 'Условия', list: true },
    { key: 'limits', label: 'Пределы', required: true, list: true }, { key: 'exceptions', label: 'Исключения', list: true },
    { key: 'consequences', label: 'Последствия', list: true }],
  decision: [{ key: 'decision', label: 'Принятое решение', required: true }, { key: 'conditions', label: 'Условия', list: true },
    { key: 'rationale', label: 'Причины', list: true }, { key: 'consequences', label: 'Последствия', list: true }],
  procedure: [{ key: 'goal', label: 'Цель', required: true }, { key: 'applicability_conditions', label: 'Когда применять', list: true },
    { key: 'required_approvals', label: 'Необходимые согласования', list: true },
    { key: 'prechecks', label: 'Проверки перед началом', required: true, list: true },
    { key: 'verification', label: 'Проверка результата', required: true, list: true }, { key: 'exceptions', label: 'Исключения', list: true }],
};
const scopeTypes = [{ key: 'product', label: 'Продукты' }, { key: 'project', label: 'Проекты' }, { key: 'team', label: 'Команды' }] as const;

function initialContent(candidate: ShadowMemoryCandidate): Record<string, unknown> {
  if (candidate.content && Object.keys(candidate.content).length) return candidate.content;
  try {
    const parsed: unknown = JSON.parse(candidate.content_text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch { return {}; }
}
const asList = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
const asSteps = (value: unknown): Step[] => Array.isArray(value) ? value.map((item) => {
  const row = item && typeof item === 'object' ? item as Record<string, unknown> : {};
  return { instruction: String(row.instruction ?? ''), expected_result: String(row.expected_result ?? ''), confirmation_required: row.confirmation_required === true };
}) : [];

export default function MemoryReviewDialog({ candidate, scopes, pending, onClose, onApprove }: Props) {
  const evidenceQuery = useQuery({ queryKey: ['admin', 'memory', 'candidate-evidence', candidate.id],
    queryFn: () => adminApi.getShadowCandidateEvidence(candidate.id), retry: false });
  const isTerm = candidate.candidate_type === 'term';
  const glossaryQuery = useQuery({ queryKey: ['admin', 'glossary'], queryFn: () => adminApi.getGlossary(), enabled: isTerm });
  const publishedTerm = glossaryQuery.data?.find((term) => term.normalized_term === candidate.normalized_subject);
  const [replaceDefinition, setReplaceDefinition] = useState(false);
  const [replacementReason, setReplacementReason] = useState('');
  const [content, setContent] = useState<Record<string, unknown>>(() => initialContent(candidate));
  const normalizedDefinition = (value: unknown) => String(value ?? '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const definitionChanged = Boolean(publishedTerm && normalizedDefinition(publishedTerm.definition) !==
    normalizedDefinition(content.definition));
  const [optionalOpen, setOptionalOpen] = useState(() => {
    const initial = initialContent(candidate);
    return (fieldSets[candidate.candidate_type] ?? []).some((field) => !field.required &&
      (field.list ? asList(initial[field.key]).some((item) => item.trim()) : Boolean(String(initial[field.key] ?? '').trim())));
  });
  const [mode, setMode] = useState<'' | 'global' | 'project' | 'scoped'>(() => {
    const proposed = candidate.scope_candidate;
    return proposed === 'global' || proposed === 'project' || proposed === 'scoped' ? proposed : '';
  });
  const [projectId, setProjectId] = useState(candidate.project_ids.length === 1 ? candidate.project_ids[0] : '');
  const [scopeIds, setScopeIds] = useState<string[]>(candidate.scope_ids);
  const [scopeFilter, setScopeFilter] = useState('');
  const [error, setError] = useState('');
  const activeScopes = scopes.filter((scope) => scope.lifecycle_status === 'active');
  const selectedScopes = activeScopes.filter((scope) => scopeIds.includes(scope.id));
  const fields = fieldSets[candidate.candidate_type] ?? [];
  const steps = asSteps(content.steps);
  const rollback = content.rollback && typeof content.rollback === 'object' && !Array.isArray(content.rollback)
    ? content.rollback as Record<string, unknown> : {};
  const setField = (key: string, value: unknown) => setContent((current) => ({ ...current, [key]: value }));
  const setRollback = (key: string, value: unknown) => setField('rollback', { ...rollback, [key]: value });
  const setStep = (index: number, patch: Partial<Step>) => setField('steps', steps.map((step, at) => at === index ? { ...step, ...patch } : step));

  const toggleScope = (scope: MemoryScopeAdminItem) => {
    if (scopeIds.includes(scope.id)) { setScopeIds((current) => current.filter((id) => id !== scope.id)); return; }
    const incompatible = new Set(activeScopes.filter((item) => item.scope_type === scope.scope_type && (item.is_all || scope.is_all)).map((item) => item.id));
    setScopeIds((current) => [...current.filter((id) => !incompatible.has(id)), scope.id]);
  };

  const validate = (): string | null => {
    if (isTerm && (glossaryQuery.isLoading || glossaryQuery.isError)) return 'Не удалось проверить действующее определение термина';
    for (const field of fields) {
      if (!field.required) continue;
      const value = content[field.key];
      if (field.list ? !asList(value).some((item) => item.trim()) : !String(value ?? '').trim()) return `Заполните поле «${field.label}»`;
    }
    if (candidate.candidate_type === 'rule' && !['require', 'forbid', 'allow'].includes(String(content.effect ?? ''))) return 'Выберите действие правила';
    if (candidate.candidate_type === 'procedure') {
      if (!steps.length || steps.some((step) => !step.instruction.trim() || !step.expected_result.trim())) return 'Добавьте шаги с действием и ожидаемым результатом';
      if (rollback.mode === 'steps' && !asList(rollback.steps).some((item) => item.trim())) return 'Опишите действия для отката';
      if (rollback.mode === 'not_applicable' && !String(rollback.reason ?? '').trim()) return 'Укажите, почему откат не нужен';
      if (rollback.mode !== 'steps' && rollback.mode !== 'not_applicable') return 'Выберите способ отката';
    }
    if (isTerm && definitionChanged && !replaceDefinition) return 'Укажите решение о замене определения в каталоге';
    if (isTerm && definitionChanged && !replacementReason.trim()) return 'Укажите причину замены определения';
    if (!isTerm && !mode) return 'Выберите область применимости';
    if (mode === 'project' && !projectId) return 'Выберите проект';
    if (mode === 'scoped' && !selectedScopes.length) return 'Выберите хотя бы один скоуп';
    return null;
  };

  const approve = async () => {
    setError('');
    const problem = validate();
    if (problem) { setError(problem); return; }
    try {
      const cleaned: Record<string, unknown> = {};
      for (const field of fields) cleaned[field.key] = field.list
        ? asList(content[field.key]).map((item) => item.trim()).filter(Boolean)
        : String(content[field.key] ?? '').trim();
      if (candidate.candidate_type === 'rule') cleaned.effect = content.effect;
      if (candidate.candidate_type === 'procedure') {
        cleaned.steps = steps.map((step) => ({ ...step, instruction: step.instruction.trim(), expected_result: step.expected_result.trim() }));
        cleaned.rollback = rollback.mode === 'steps'
          ? { mode: 'steps', steps: asList(rollback.steps).map((item) => item.trim()).filter(Boolean) }
          : { mode: 'not_applicable', reason: String(rollback.reason ?? '').trim() };
      }
      const decision: MemoryApproval = { content: cleaned };
      if (isTerm && definitionChanged) {
        decision.replace_existing_definition = replaceDefinition;
        decision.reason = replacementReason.trim();
      }
      if (!isTerm && mode) {
        decision.scope = mode;
        if (mode === 'project') decision.project_id = projectId;
        if (mode === 'scoped') decision.scope_ids = scopeIds;
      }
      await onApprove(decision);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось утвердить запись'); }
  };

  const blockedByConflict = candidate.conflict_ids.length > 0;
  const filteredScopes = activeScopes.filter((scope) => [scope.name, scope.key, ...scope.aliases].join(' ').toLocaleLowerCase().includes(scopeFilter.trim().toLocaleLowerCase()));
  const optionalFields = fields.filter((field) => !field.required);
  const renderField = (field: Field) => <label key={field.key} className={styles.field}><span>{field.label}{field.required && <em> *</em>}</span>
    <textarea rows={field.list ? 3 : 2} maxLength={field.list ? undefined : 500} placeholder={field.list ? 'Один пункт на строку' : undefined}
      value={field.list ? asList(content[field.key]).join('\n') : String(content[field.key] ?? '')}
      onChange={(event) => setField(field.key, field.list ? event.target.value.split('\n') : event.target.value)} />
    {field.list && <small>Каждый пункт — с новой строки</small>}
  </label>;
  return (
    <Modal open title="Утверждение памяти" onClose={onClose} size="lg" bodyClassName={styles.body}
      footer={<><Button variant="outline" onClick={onClose}>Закрыть</Button><Button disabled={pending || blockedByConflict} onClick={approve}>{pending ? 'Сохраняю…' : 'Утвердить запись'}</Button></>}>
      <div className={styles.layout}>
        <header className={styles.intro}><div className={styles.eyebrow}><Badge tone="info">{typeLabels[candidate.candidate_type] ?? candidate.candidate_type}</Badge><span>Предложено из документа</span></div>
          <h2>{candidate.subject}</h2><p>Проверьте формулировку и укажите, где её можно применять.</p></header>
        {blockedByConflict && <div className={styles.warning} role="alert"><strong>Есть нерешённый конфликт</strong><span>Эту запись пока нельзя утвердить. Сначала разрешите конфликт в очереди проверки.</span></div>}
        {isTerm && publishedTerm && <div className={styles.warning}>
          <strong>Определение в каталоге</strong><span>{publishedTerm.definition}</span>
          {definitionChanged && <>
            <label className={styles.check}><input type="checkbox" checked={replaceDefinition} onChange={(event) => setReplaceDefinition(event.target.checked)} /> Заменить определение источником из этого документа</label>
            {replaceDefinition && <label className={styles.field}><span>Причина замены *</span><textarea rows={2} maxLength={2000} value={replacementReason} onChange={(event) => setReplacementReason(event.target.value)} /></label>}
          </>}
        </div>}
        {!candidate.content_valid && <div className={styles.warning} role="alert"><strong>Извлечённое содержание было неполным</strong><span>{candidate.content_error ?? 'Часть полей отсутствовала.'} Проверьте поля ниже перед утверждением.</span></div>}
        <section className={styles.section} aria-labelledby="memory-content-heading">
          <div className={styles.sectionHead}><span className={styles.number}>1</span><div><h3 id="memory-content-heading">Содержание</h3><p>Так формулировка будет храниться в памяти.</p></div></div>
          <div className={styles.fields}>
            {fields.filter((field) => field.required).map(renderField)}
            {candidate.candidate_type === 'rule' && <label className={styles.field}><span>Действие правила *</span><select value={String(content.effect ?? '')} onChange={(event) => setField('effect', event.target.value)}>
              <option value="">Выберите действие</option><option value="require">Требует</option><option value="forbid">Запрещает</option><option value="allow">Разрешает</option></select></label>}
            {optionalFields.length > 0 && <details className={styles.optional} open={optionalOpen} onToggle={(event) => setOptionalOpen(event.currentTarget.open)}><summary>Дополнительные условия и детали</summary><div className={styles.fields}>{optionalFields.map(renderField)}</div></details>}
            {candidate.candidate_type === 'procedure' && <>
              <div className={styles.subsection}><div className={styles.subsectionHead}><strong>Шаги процедуры *</strong><Button size="sm" variant="outline" onClick={() => setField('steps', [...steps, { instruction: '', expected_result: '', confirmation_required: false }])}>Добавить шаг</Button></div>
                {steps.length === 0 && <p className={styles.hint}>Добавьте последовательность действий.</p>}
                {steps.map((step, index) => <div className={styles.stepCard} key={index}><div className={styles.subsectionHead}><strong>Шаг {index + 1}</strong><Button size="sm" variant="ghost" onClick={() => setField('steps', steps.filter((_, at) => at !== index))}>Убрать</Button></div>
                  <label className={styles.field}><span>Действие</span><textarea rows={2} maxLength={500} value={step.instruction} onChange={(event) => setStep(index, { instruction: event.target.value })} /></label>
                  <label className={styles.field}><span>Ожидаемый результат</span><textarea rows={2} maxLength={500} value={step.expected_result} onChange={(event) => setStep(index, { expected_result: event.target.value })} /></label>
                  <label className={styles.check}><input type="checkbox" checked={step.confirmation_required} onChange={(event) => setStep(index, { confirmation_required: event.target.checked })} /> Требуется подтверждение</label></div>)}
              </div>
              <div className={styles.subsection}><strong>Откат *</strong><div className={styles.modeChoices}>
                <label><input type="radio" name="rollback" checked={rollback.mode === 'steps'} onChange={() => setField('rollback', { mode: 'steps', steps: asList(rollback.steps) })} /> Есть действия для отката</label>
                <label><input type="radio" name="rollback" checked={rollback.mode === 'not_applicable'} onChange={() => setField('rollback', { mode: 'not_applicable', reason: String(rollback.reason ?? '') })} /> Откат не требуется</label></div>
                {rollback.mode === 'steps' && <label className={styles.field}><span>Действия для отката</span><textarea rows={3} placeholder="Одно действие на строку" value={asList(rollback.steps).join('\n')} onChange={(event) => setRollback('steps', event.target.value.split('\n'))} /></label>}
                {rollback.mode === 'not_applicable' && <label className={styles.field}><span>Почему откат не нужен</span><textarea rows={2} maxLength={500} value={String(rollback.reason ?? '')} onChange={(event) => setRollback('reason', event.target.value)} /></label>}
              </div>
            </>}
          </div>
        </section>
        {!isTerm && <section className={styles.section} aria-labelledby="memory-scope-heading"><div className={styles.sectionHead}><span className={styles.number}>2</span><div><h3 id="memory-scope-heading">Где применять</h3><p>Выберите область, в которой утверждение действительно.</p></div></div>
          <div className={styles.scopeChoices}>
            <label className={mode === 'global' ? styles.choiceActive : styles.choice}><input type="radio" name="applicability" checked={mode === 'global'} onChange={() => setMode('global')} /><span><strong>Везде</strong><small>Для всей компании, без ограничений по скоупам</small></span></label>
            <label className={mode === 'scoped' ? styles.choiceActive : styles.choice}><input type="radio" name="applicability" checked={mode === 'scoped'} onChange={() => setMode('scoped')} /><span><strong>Выбранные скоупы</strong><small>Для конкретных продуктов, проектов или команд</small></span></label>
            {candidate.project_ids.length > 0 && <label className={mode === 'project' ? styles.choiceActive : styles.choice}><input type="radio" name="applicability" checked={mode === 'project'} onChange={() => setMode('project')} /><span><strong>Один проект</strong><small>Совместимый режим для связанного проекта</small></span></label>}
          </div>
          {mode === 'scoped' && <div className={styles.scopePicker}><p className={styles.hint}>Можно выбрать несколько значений одного типа. Если выбраны разные типы, утверждение действует при совпадении каждого типа.</p>
            <Input aria-label="Поиск скоупа" placeholder="Найти продукт, проект или команду" value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value)} />
            {selectedScopes.length > 0 && <div className={styles.selectedScopes}>{selectedScopes.map((scope) => <Badge key={scope.id} tone="info">{scope.name}</Badge>)}</div>}
            <div className={styles.scopeList}>{scopeTypes.map(({ key, label }) => { const options = filteredScopes.filter((scope) => scope.scope_type === key);
              return options.length > 0 && <fieldset key={key}><legend>{label}</legend>{options.map((scope) => <label key={scope.id} className={styles.scopeOption}><input type="checkbox" checked={scopeIds.includes(scope.id)} onChange={() => toggleScope(scope)} /><span>{scope.name}<small>{scope.key}{scope.is_all ? ' · все' : ''}</small></span></label>)}</fieldset>;
            })}{filteredScopes.length === 0 && <p className={styles.hint}>Подходящих активных скоупов нет.</p>}</div>
          </div>}
          {mode === 'project' && <label className={styles.field}><span>Проект</span><select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Выберите проект</option>{candidate.project_ids.map((id) => { const linked = activeScopes.find((scope) => scope.project_id === id); return <option key={id} value={id}>{linked?.name ?? id}</option>; })}</select></label>}
        </section>}
        <section className={styles.section} aria-labelledby="memory-evidence-heading"><div className={styles.sectionHead}><span className={styles.number}>{isTerm ? '2' : '3'}</span><div><h3 id="memory-evidence-heading">Основание</h3><p>Сверьте формулировку с текстом документа.</p></div></div>
          <div className={styles.evidence}><span>Фрагментов документа: <strong>{candidate.evidence_section_ids.length}</strong></span><span>Уверенность извлечения: <strong>{Math.round(candidate.extraction_confidence * 100)}%</strong></span></div>
          {evidenceQuery.isLoading && <p className={styles.hint}>Загружаю исходные фрагменты…</p>}
          {evidenceQuery.data && <div className={styles.source}><strong>{evidenceQuery.data.document_title}</strong>
            {evidenceQuery.data.sections.length > 0 ? evidenceQuery.data.sections.map((section) => <blockquote key={section.id} className={styles.excerpt}><span>{section.label}</span><p>{section.text}</p></blockquote>)
              : <p className={styles.hint}>Текст исходных фрагментов не найден в текущей версии документа.</p>}
          </div>}
          {evidenceQuery.isError && <p className={styles.hint}>Не удалось загрузить текст документа. Перед утверждением проверьте источник отдельно.</p>}
          <details className={styles.details}><summary>Подсказки извлечения</summary>
            {candidate.evidence_section_ids.length > 0 && <div><strong>Идентификаторы фрагментов</strong><p>{candidate.evidence_section_ids.join(', ')}</p></div>}
            {!isTerm && <div><strong>Предложенная применимость</strong><p>{candidate.scope_candidate || 'Не определена'}{candidate.scope_keys.length > 0 ? ` · ${candidate.scope_keys.join(', ')}` : ''}</p></div>}
            {candidate.scope_rationale && <div><strong>Обоснование</strong><p>{candidate.scope_rationale}</p></div>}
            {candidate.mentioned_scope_keys.length > 0 && <div><strong>Упомянуты без доказанной применимости</strong><p>{candidate.mentioned_scope_keys.join(', ')}</p></div>}
            {candidate.unmatched_scope_names.length > 0 && <div><strong>Не найдены в каталоге скоупов</strong><p>{candidate.unmatched_scope_names.join(', ')}</p></div>}
          </details>
        </section>
        {error && <div className={styles.warning} role="alert">{error}</div>}
      </div>
    </Modal>
  );
}

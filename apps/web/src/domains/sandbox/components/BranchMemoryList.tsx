import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/shared/ui';
import { InspectorExpandableValue, InspectorFieldGroup, InspectorFieldRow, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { SandboxBranchMemory, SandboxSelectedItem } from '../types';
import styles from './BranchMemoryList.module.css';

type Row = Record<string, unknown>;
type MemoryKind = NonNullable<SandboxSelectedItem['memoryKind']>;

function scalar(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.map(scalar).join(', ') || '—';
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : '—';
}

function contextRows(context: Record<string, unknown>, artifactsOnly: boolean): Row[] {
  const artifacts = Array.isArray(context.artifacts) ? context.artifacts as Row[] : [];
  if (artifactsOnly) return artifacts.map((item) => ({ ...item, _context_kind: 'artifact' }));
  const result: Row[] = [];
  if (context.active_goal) result.push({ ...(context.active_goal as Row), _context_kind: 'goal' });
  if (context.focus) result.push({ ...(context.focus as Row), _context_kind: 'focus' });
  for (const [key, label] of [['open_loops', 'open_loop'], ['decisions', 'decision'], ['term_bindings', 'term_binding'], ['task_results', 'task_result']] as const) {
    if (Array.isArray(context[key])) result.push(...(context[key] as Row[]).map((item) => ({ ...item, _context_kind: label })));
  }
  if (context.recent_anchor) result.push({ ...(context.recent_anchor as Row), _context_kind: 'recent_anchor' });
  return result;
}

function rows(memory: SandboxBranchMemory, kind: MemoryKind): Row[] {
  if (kind === 'user_facts') return memory.user_facts;
  if (kind === 'tenant_facts') return memory.tenant_facts;
  if (kind === 'glossary') return memory.glossary;
  if (kind === 'project_memory') return memory.project_memory;
  return contextRows(memory.chat_context, kind === 'chat_artifacts');
}

function titleFor(item: Row, kind: MemoryKind): string {
  if (kind === 'glossary') return scalar(item.term);
  if (kind === 'project_memory') return scalar(item.subject);
  if (kind === 'chat_artifacts') return scalar(item.file_name);
  const label = scalar(item._context_kind);
  return ({ goal: 'Цель', focus: 'Фокус', open_loop: 'Открытый вопрос', decision: 'Решение', term_binding: 'Термин', task_result: 'Результат задачи', recent_anchor: 'Последний ориентир' }[label] ?? scalar(item.subject));
}

function previewFor(item: Row, kind: MemoryKind): string {
  if (kind === 'glossary') return scalar(item.description);
  if (kind === 'project_memory') return scalar(item.content);
  if (kind === 'chat_artifacts') return scalar(item.role);
  return scalar(item.value ?? item.text ?? item.user_message ?? item.term ?? item.safe_summary ?? item.assistant_outcome ?? item.topic);
}

function FactInspector({ item }: { item: Row }) {
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Scope"><InspectorScalar value={scalar(item.scope)} /></InspectorFieldRow>
    <InspectorFieldRow label="Значение"><InspectorTextBlock text={scalar(item.value)} /></InspectorFieldRow>
    <InspectorFieldRow label="Статус"><InspectorStatus label={scalar(item.status)} tone={item.status === 'confirmed' ? 'success' : 'warn'} /></InspectorFieldRow>
    <InspectorFieldRow label="Источник"><InspectorScalar value={scalar(item.source)} /></InspectorFieldRow>
    <InspectorFieldRow label="Доверие"><InspectorScalar value={typeof item.confidence === 'number' ? `${Math.round(item.confidence * 100)}%` : '—'} /></InspectorFieldRow>
    <InspectorFieldRow label="Подтверждений"><InspectorScalar value={scalar(item.support_count)} /></InspectorFieldRow>
    <InspectorFieldRow label="Ревизия"><InspectorScalar value={scalar(item.revision)} /></InspectorFieldRow>
    <InspectorFieldRow label="Source reference"><InspectorScalar value={scalar(item.source_ref)} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

function GlossaryInspector({ item }: { item: Row }) {
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Определение"><InspectorTextBlock text={scalar(item.description)} /></InspectorFieldRow>
    <InspectorFieldRow label="Алиасы"><InspectorScalar value={scalar(item.aliases)} /></InspectorFieldRow>
    <InspectorFieldRow label="Scope"><InspectorScalar value={scalar(item.scope)} /></InspectorFieldRow>
    <InspectorFieldRow label="Проект"><InspectorScalar value={scalar(item.project_key)} /></InspectorFieldRow>
    <InspectorFieldRow label="Тип сущности"><InspectorScalar value={scalar(item.entity_type)} /></InspectorFieldRow>
    <InspectorFieldRow label="Статус"><InspectorStatus label={scalar(item.status)} tone={item.status === 'confirmed' ? 'success' : 'warn'} /></InspectorFieldRow>
    <InspectorFieldRow label="Подтверждений"><InspectorScalar value={scalar(item.support_count)} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

function ProjectMemoryInspector({ item }: { item: Row }) {
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Содержание"><InspectorTextBlock text={scalar(item.content)} /></InspectorFieldRow>
    <InspectorFieldRow label="Тип"><InspectorScalar value={scalar(item.item_type)} /></InspectorFieldRow>
    <InspectorFieldRow label="Проект"><InspectorScalar value={scalar(item.project_key)} /></InspectorFieldRow>
    <InspectorFieldRow label="Состояние"><InspectorStatus label={scalar(item.state)} tone={item.state === 'active' ? 'success' : 'warn'} /></InspectorFieldRow>
    <InspectorFieldRow label="Доверие"><InspectorScalar value={typeof item.confidence === 'number' ? `${Math.round(item.confidence * 100)}%` : '—'} /></InspectorFieldRow>
    <InspectorFieldRow label="Источников"><InspectorScalar value={scalar(item.source_count)} /></InspectorFieldRow>
    <InspectorFieldRow label="Последняя проверка"><InspectorScalar value={scalar(item.last_verified_at)} /></InspectorFieldRow>
    <InspectorFieldRow label="Применимость"><InspectorExpandableValue value={item.applicability ?? {}} title="Применимость" /></InspectorFieldRow>
    <InspectorFieldRow label="Видимость"><InspectorExpandableValue value={item.visibility ?? {}} title="Видимость" /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

function ContextInspector({ item, artifact }: { item: Row; artifact: boolean }) {
  if (artifact) return <InspectorFieldGroup>
    <InspectorFieldRow label="Роль"><InspectorScalar value={scalar(item.role)} /></InspectorFieldRow>
    <InspectorFieldRow label="Тип"><InspectorScalar value={scalar(item.content_type)} /></InspectorFieldRow>
    <InspectorFieldRow label="Размер"><InspectorScalar value={item.size_bytes === undefined ? '—' : `${scalar(item.size_bytes)} B`} /></InspectorFieldRow>
  </InspectorFieldGroup>;
  const entries = Object.entries(item).filter(([key]) => !key.startsWith('_') && !key.endsWith('_trust_class'));
  return <InspectorFieldGroup>{entries.map(([key, value]) => <InspectorFieldRow key={key} label={key.replace(/_/g, ' ')}>
    {typeof value === 'string' && value.length > 140 ? <InspectorTextBlock text={value} /> : <InspectorExpandableValue value={value} title={key} />}
  </InspectorFieldRow>)}</InspectorFieldGroup>;
}

function MemoryInspector({ item, kind }: { item: Row; kind: MemoryKind }) {
  if (kind === 'user_facts' || kind === 'tenant_facts') return <FactInspector item={item} />;
  if (kind === 'glossary') return <GlossaryInspector item={item} />;
  if (kind === 'project_memory') return <ProjectMemoryInspector item={item} />;
  return <ContextInspector item={item} artifact={kind === 'chat_artifacts'} />;
}

export function BranchMemoryList({ memory, kind, isLoading, isError }: {
  memory?: SandboxBranchMemory;
  kind: MemoryKind;
  isLoading: boolean;
  isError: boolean;
}) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const items = useMemo(() => memory ? rows(memory, kind) : [], [memory, kind]);
  useEffect(() => setSelectedIndex(null), [kind, memory?.branch_id]);
  if (isLoading) return <p>Загружаю память ветки…</p>;
  if (isError || !memory) return <p>Не удалось загрузить память ветки.</p>;
  if (!items.length) return <p>В этом разделе пока нет записей.</p>;
  const selected = selectedIndex === null ? null : items[selectedIndex];
  if (selected) return <div className={styles.inspector}>
    <Button size="sm" variant="outline" onClick={() => setSelectedIndex(null)}>← К списку</Button>
    <h3 className={styles.inspectorTitle}>{titleFor(selected, kind)}</h3>
    <MemoryInspector item={selected} kind={kind} />
  </div>;
  return <div className={styles.rows}>{items.map((item, index) => <button type="button" className={styles.row} key={`${titleFor(item, kind)}:${index}`} onClick={() => setSelectedIndex(index)}>
    <span className={styles.main}><span className={styles.subject}>{titleFor(item, kind)}</span><span className={styles.value}>{previewFor(item, kind)}</span></span>
  </button>)}</div>;
}

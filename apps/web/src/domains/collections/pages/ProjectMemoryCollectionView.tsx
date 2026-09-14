import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import {
  collectionsApi,
  type ProjectMemoryItem,
  type ProjectMemoryProject,
} from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  Icon,
  Input,
  Modal,
  Skeleton,
  type DataTableColumn,
} from '@/shared/ui';
import styles from './ProjectMemoryCollectionView.module.css';

const PROJECT_COLUMNS: DataTableColumn<ProjectMemoryProject>[] = [
  {
    key: 'name',
    label: 'ПРОЕКТ',
    sortable: true,
    render: (project) => (
      <div>
        <strong>{project.name}</strong>
        <div className={styles.projectKey}>{project.key}</div>
      </div>
    ),
  },
  {
    key: 'items',
    label: 'ЗНАНИЙ',
    width: 110,
    align: 'right',
    sortValue: (project) => totalFacts(project),
    render: (project) => totalFacts(project).toLocaleString(),
  },
  {
    key: 'status',
    label: 'СТАТУСЫ',
    width: 180,
    render: (project) => <ProjectStatusSummary project={project} />,
  },
];

const ITEM_COLUMNS: DataTableColumn<ProjectMemoryItem>[] = [
  {
    key: 'subject',
    label: 'КЛЮЧ',
    width: 260,
    sortable: true,
    render: (fact) => <code className={styles.factKey}>{fact.subject}</code>,
  },
  {
    key: 'value',
    label: 'ЗНАНИЕ',
    render: (fact) => <MemoryContent fact={fact} />,
  },
  {
    key: 'kind',
    label: 'ТИП',
    width: 130,
    render: (fact) => <Badge tone="neutral">{fact.kind}</Badge>,
  },
  {
    key: 'status',
    label: 'СТАТУС',
    width: 150,
    render: (fact) => <FactStatusBadge status={fact.status} />,
  },
];

export default function ProjectMemoryCollectionView() {
  const navigate = useNavigate();
  const [selectedProjectKey, setSelectedProjectKey] = useState<string | null>(null);
  const [projectQueryText, setProjectQueryText] = useState('');
  const [itemQueryText, setItemQueryText] = useState('');
  const [itemType, setItemType] = useState('');
  const [itemState, setItemState] = useState('');
  const overviewQuery = useQuery({
    queryKey: qk.collections.projectMemoryOverview({ query: projectQueryText }),
    queryFn: () => collectionsApi.getProjectMemoryOverview({ query: projectQueryText || undefined }),
  });
  const projectQuery = useQuery({
    queryKey: qk.collections.projectMemoryProject(selectedProjectKey ?? '', { query: itemQueryText, item_type: itemType, state: itemState }),
    queryFn: () => collectionsApi.getProjectMemoryProject(selectedProjectKey!, {
      query: itemQueryText || undefined,
      item_type: itemType || undefined,
      state: itemState || undefined,
    }),
    enabled: selectedProjectKey !== null,
  });

  if (overviewQuery.isLoading) {
    return <div className={styles.loading}><Skeleton width={520} height={240} /></div>;
  }

  if (overviewQuery.isError) {
    return (
      <EmptyState
        title="Не удалось загрузить Project Memory"
        description="Попробуйте обновить страницу позже."
      />
    );
  }

  const projects = overviewQuery.data?.projects ?? [];
  const selectedProject = projects.find((project) => project.key === selectedProjectKey);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Button
            variant="outline"
            aria-label="Вернуться к коллекциям"
            onClick={() => navigate('/gpt/collections')}
          >
            <Icon name="chevron-left" size={18} />
          </Button>
          <div>
            <h1>Project Memory</h1>
            <p>Факты, правила и инструкции, привязанные к проектам.</p>
          </div>
        </div>
      </header>

      {projects.length === 0 ? (
        <EmptyState
          title="В Project Memory пока нет фактов"
          description="Подтверждённые, ожидающие и требующие проверки факты появятся здесь по проектам."
        />
      ) : (
        <div className={styles.content}>
          <section className={styles.projectsSection} aria-label="Проекты">
            <h2>Проекты</h2>
            <Input aria-label="Поиск проектов" placeholder="Поиск проекта" value={projectQueryText} onChange={(event) => setProjectQueryText(event.target.value)} />
            <DataTable
              columns={PROJECT_COLUMNS}
              data={projects}
              keyField="key"
              emptyText="Проекты не найдены"
              onRowClick={(project) => setSelectedProjectKey(project.key)}
              rowClassName={(project) => project.key === selectedProjectKey ? styles.selectedRow : undefined}
            />
          </section>

          <section className={styles.factsSection} aria-live="polite">
            {selectedProject === undefined ? (
              <EmptyState
                title="Выберите проект"
                description="Нажмите на строку проекта, чтобы посмотреть его факты."
              />
            ) : projectQuery.isLoading ? (
              <div className={styles.loading}><Skeleton width={520} height={200} /></div>
            ) : projectQuery.isError || projectQuery.data === undefined ? (
              <EmptyState
                title="Не удалось загрузить факты проекта"
                description="Попробуйте выбрать проект ещё раз."
              />
            ) : (
              <>
                <div className={styles.factsHeader}>
                  <div>
                    <h2>{projectQuery.data.project.name}</h2>
                    <span>{projectQuery.data.project.key}</span>
                  </div>
                  <ProjectStatusSummary project={projectQuery.data.project} />
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                  <Input aria-label="Поиск знаний" placeholder="Поиск по subject и содержимому" value={itemQueryText} onChange={(event) => setItemQueryText(event.target.value)} />
                  <select aria-label="Тип знания" value={itemType} onChange={(event) => setItemType(event.target.value)}>
                    <option value="">Все типы</option>
                    <option value="description">Описание</option>
                    <option value="relationship">Связь</option>
                    <option value="rule">Правило</option>
                    <option value="constraint">Ограничение</option>
                    <option value="procedure">Процедура</option>
                    <option value="decision">Решение</option>
                  </select>
                  <select aria-label="Состояние знания" value={itemState} onChange={(event) => setItemState(event.target.value)}>
                    <option value="">Все состояния</option>
                    <option value="active">Актуально</option>
                    <option value="uncertain">Требует проверки</option>
                    <option value="stale">Устарело</option>
                  </select>
                </div>
                <DataTable
                  columns={ITEM_COLUMNS}
                  data={projectQuery.data.items}
                  keyField="id"
                  emptyText="Текущих знаний нет"
                />
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function totalFacts(project: ProjectMemoryProject): number {
  return Object.values(project.status_counts).reduce((total, count) => total + count, 0);
}

function ProjectStatusSummary({ project }: { project: ProjectMemoryProject }) {
  return (
    <div className={styles.statusSummary}>
      {project.status_counts.active ? <FactStatusBadge status="active" count={project.status_counts.active} /> : null}
      {project.status_counts.uncertain ? <FactStatusBadge status="uncertain" count={project.status_counts.uncertain} /> : null}
      {project.status_counts.stale ? <FactStatusBadge status="stale" count={project.status_counts.stale} /> : null}
    </div>
  );
}

function FactStatusBadge({ status, count }: { status: string; count?: number }) {
  const statusMap: Record<string, { label: string; tone: 'success' | 'warn' | 'danger' }> = {
    active: { label: 'Актуально', tone: 'success' },
    uncertain: { label: 'Требует проверки', tone: 'warn' },
    stale: { label: 'Устарело', tone: 'danger' },
  };
  const view = statusMap[status] ?? { label: status, tone: 'warn' as const };
  return <Badge tone={view.tone}>{count === undefined ? view.label : `${view.label}: ${count}`}</Badge>;
}

function MemoryContent({ fact }: { fact: ProjectMemoryItem }) {
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const evidenceQuery = useQuery({
    queryKey: ['collections', 'project-memory', 'evidence', fact.id, selectedEvidenceId],
    queryFn: () => collectionsApi.getProjectMemoryEvidence(fact.id, selectedEvidenceId!),
    enabled: selectedEvidenceId !== null,
  });
  const evidenceControls = fact.evidence_section_ids.length > 0 ? (
    <details>
      <summary>Evidence ({fact.evidence_section_ids.length})</summary>
      {fact.evidence_section_ids.map((sectionId) => <Button key={sectionId} size="sm" variant="ghost" onClick={() => setSelectedEvidenceId(sectionId)}>{sectionId}</Button>)}
      <Modal open={selectedEvidenceId !== null} onClose={() => setSelectedEvidenceId(null)} title={evidenceQuery.data?.label ?? 'Evidence'}>
        {evidenceQuery.isLoading ? 'Загрузка evidence…' : evidenceQuery.isError ? 'Evidence недоступен.' : <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{evidenceQuery.data?.excerpt}</pre>}
      </Modal>
    </details>
  ) : null;
  if (fact.kind !== 'procedure') {
    const summary = typeof fact.content.summary === 'string' ? fact.content.summary : fact.value;
    return <><span className={styles.factValue}>{summary}</span>{evidenceControls}</>;
  }
  const content = fact.content;
  const goal = typeof content.goal === 'string' ? content.goal : fact.subject;
  const conditions = Array.isArray(content.applicability_conditions) ? content.applicability_conditions : [];
  const approvals = Array.isArray(content.required_approvals) ? content.required_approvals : [];
  const prechecks = Array.isArray(content.prechecks) ? content.prechecks : [];
  const steps = Array.isArray(content.steps) ? content.steps : [];
  const verification = Array.isArray(content.verification) ? content.verification : [];
  const rollback = content.rollback && typeof content.rollback === 'object' ? content.rollback as Record<string, unknown> : null;
  const exceptions = Array.isArray(content.exceptions) ? content.exceptions : [];
  return (
    <div className={styles.procedure}>
      <strong>{goal}</strong>
      {conditions.length > 0 ? <div>Условия: {conditions.map(String).join('; ')}</div> : null}
      {approvals.length > 0 ? <div>Согласования: {approvals.map(String).join('; ')}</div> : null}
      {prechecks.length > 0 ? <div>Предварительные проверки: {prechecks.map(String).join('; ')}</div> : null}
      {steps.length > 0 ? <ol>{steps.map((step, index) => {
        const value = step as Record<string, unknown>;
        return <li key={index}>{String(value.instruction ?? '')}{value.expected_result ? ` — результат: ${String(value.expected_result)}` : ''}{value.confirmation_required ? ' (требуется подтверждение)' : ''}</li>;
      })}</ol> : null}
      {verification.length > 0 ? <span>Проверка: {verification.map(String).join('; ')}</span> : null}
      {rollback ? <div>Откат: {String(rollback.mode === 'steps' ? (rollback.steps as unknown[] | undefined)?.map(String).join('; ') : rollback.reason ?? 'не применим')}</div> : null}
      {exceptions.length > 0 ? <div>Исключения: {exceptions.map(String).join('; ')}</div> : null}
      {evidenceControls}
    </div>
  );
}

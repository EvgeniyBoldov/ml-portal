import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import {
  collectionsApi,
  type ProjectMemoryFact,
  type ProjectMemoryProject,
} from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  Icon,
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
    key: 'facts',
    label: 'ФАКТОВ',
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

const FACT_COLUMNS: DataTableColumn<ProjectMemoryFact>[] = [
  {
    key: 'subject',
    label: 'КЛЮЧ',
    width: 260,
    sortable: true,
    render: (fact) => <code className={styles.factKey}>{fact.subject}</code>,
  },
  {
    key: 'value',
    label: 'ЗНАЧЕНИЕ',
    render: (fact) => <span className={styles.factValue}>{fact.value}</span>,
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
  const overviewQuery = useQuery({
    queryKey: qk.collections.projectMemoryOverview(),
    queryFn: () => collectionsApi.getProjectMemoryOverview(),
  });
  const projectQuery = useQuery({
    queryKey: qk.collections.projectMemoryProject(selectedProjectKey ?? ''),
    queryFn: () => collectionsApi.getProjectMemoryProject(selectedProjectKey!),
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
                <DataTable
                  columns={FACT_COLUMNS}
                  data={projectQuery.data.facts}
                  keyField="subject"
                  emptyText="Текущих фактов нет"
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
      {project.status_counts.confirmed ? <FactStatusBadge status="confirmed" count={project.status_counts.confirmed} /> : null}
      {project.status_counts.pending ? <FactStatusBadge status="pending" count={project.status_counts.pending} /> : null}
      {project.status_counts.unconfirmed ? <FactStatusBadge status="unconfirmed" count={project.status_counts.unconfirmed} /> : null}
    </div>
  );
}

function FactStatusBadge({ status, count }: { status: string; count?: number }) {
  const statusMap: Record<string, { label: string; tone: 'success' | 'warn' | 'danger' }> = {
    confirmed: { label: 'Подтверждён', tone: 'success' },
    pending: { label: 'Ожидает', tone: 'warn' },
    unconfirmed: { label: 'Требует проверки', tone: 'danger' },
  };
  const view = statusMap[status] ?? { label: status, tone: 'warn' as const };
  return <Badge tone={view.tone}>{count === undefined ? view.label : `${view.label}: ${count}`}</Badge>;
}

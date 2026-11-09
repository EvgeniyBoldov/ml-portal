import { useEffect, useState } from 'react';
import { InspectorTextBlock, InspectorStatus } from '@/shared/ui/Inspector';
import Modal from '@/shared/ui/Modal';
import type {
  TraceMemoryContext,
  TraceMemoryContextItem,
} from '@/domains/sandbox/traceProjection';
import {
  InspectorEmptyState,
  InspectorSection,
  InspectorStack,
} from '../InspectorPrimitives';
import { MemoryItemsTable } from './MemoryItemsTable';

import styles from './MemoryContextViewer.module.css';

export function MemoryContextViewer({
  context,
}: {
  context?: TraceMemoryContext;
}) {
  const [selectedGroup, setSelectedGroup] = useState<{
    title: string;
    items: TraceMemoryContextItem[];
  } | null>(null);
  useEffect(() => {
    const closeFullView = () => setSelectedGroup(null);
    document.addEventListener('agent-inspector-section-change', closeFullView);
    return () =>
      document.removeEventListener(
        'agent-inspector-section-change',
        closeFullView
      );
  }, []);
  if (!context)
    return (
      <InspectorEmptyState message="Контекст памяти не записан в журнал." />
    );
  const groups: {
    title: string;
    items: TraceMemoryContextItem[];
    showScope?: boolean;
    error?: string;
    status?: string;
  }[] = [
    {
      title: 'Факты пользователя',
      items: context.context.filter(
        item => item.type === 'fact' && item.scope === 'user'
      ),
    },
    {
      title: 'Факты рабочей группы',
      items: context.context.filter(
        item => item.type === 'fact' && item.scope === 'tenant'
      ),
    },
    {
      title: 'Глоссарий',
      items: context.context.filter(item => item.type === 'glossary'),
    },
    ...(context.scopeGroups?.length
      ? context.scopeGroups.map(group => ({
          title: `Память · ${group.scope}`,
          items: context.context.filter(
            item => item.type === 'knowledge' && item.scope === group.scope
          ),
          status: group.status,
          error: group.error,
        }))
      : [
          {
            title: 'Долговременная память',
            items: context.context.filter(item => item.type === 'knowledge'),
          },
        ]),
    {
      title: 'Проекты',
      items: context.context.filter(item => item.type === 'project'),
    },
    {
      title: 'Другие факты контекста',
      items: context.context.filter(
        item => item.type === 'fact' && !['user', 'tenant'].includes(item.scope)
      ),
      showScope: true,
    },
  ];
  return (
    <InspectorStack>
      <p className={styles.intro}>
        Контекст, доступный агенту при выполнении задачи.
      </p>
      {context.scopeCandidates ? (
        <InspectorSection
          title={`Кандидаты области${context.truncated ? ' · список сокращён' : ''}`}
        >
          <InspectorTextBlock
            text={JSON.stringify(context.scopeCandidates, null, 2)}
          />
        </InspectorSection>
      ) : null}
      {context.scopeAmbiguities?.length ? (
        <InspectorSection title="Неоднозначность области">
          <InspectorTextBlock
            text={JSON.stringify(context.scopeAmbiguities, null, 2)}
          />
        </InspectorSection>
      ) : null}
      {groups
        .filter(group => group.items.length > 0 || group.status)
        .map(group => (
          <InspectorSection
            key={group.title}
            title={`${group.title} · ${group.items.length}`}
          >
            {group.items.length ? (
              <button
                type="button"
                className={styles.groupDetails}
                onClick={() =>
                  setSelectedGroup({ title: group.title, items: group.items })
                }
              >
                {group.items.length > 10 ? `Все записи (${group.items.length})` : 'Увеличить таблицу'}
              </button>
            ) : null}
            {group.status === 'failed' ? (
              <InspectorStatus
                label={group.error || 'Последний поиск завершился ошибкой'}
                tone="warn"
              />
            ) : null}
            {group.items.length ? (
              <MemoryItemsTable
                items={group.items}
                showScope={group.showScope}
                previewLimit={10}
              />
            ) : (
              <InspectorEmptyState
                message={
                  group.status === 'failed'
                    ? 'Найденных фрагментов нет.'
                    : 'Поиск выполнен, фрагменты не найдены.'
                }
              />
            )}
          </InspectorSection>
        ))}
      {!context.context.length && !context.scopeGroups?.length ? (
        <InspectorEmptyState message="Память не использовалась." />
      ) : null}
      {context.ambiguities.length ? (
        <InspectorSection title="Неоднозначности">
          <InspectorTextBlock text={context.ambiguities.join('\n')} />
        </InspectorSection>
      ) : null}
      {context.sourceCheckReasons.length ? (
        <InspectorSection title="Требуется проверка источника">
          <InspectorTextBlock text={context.sourceCheckReasons.join('\n')} />
        </InspectorSection>
      ) : null}
      {context.searchScope ? (
        <InspectorSection title="Параметры поиска">
          <details className={styles.technicalDetails}>
            <summary>Показать технические параметры</summary>
            <InspectorTextBlock
              text={JSON.stringify(context.searchScope, null, 2)}
            />
          </details>
        </InspectorSection>
      ) : null}
      {context.scopeCandidates?.length || context.scopeAmbiguities?.length ? (
        <InspectorSection title="Диагностика области поиска">
          <details className={styles.technicalDetails}>
            <summary>Показать детали</summary>
            {context.scopeCandidates?.length ? (
              <InspectorTextBlock
                text={JSON.stringify(context.scopeCandidates, null, 2)}
              />
            ) : null}
            {context.scopeAmbiguities?.length ? (
              <InspectorTextBlock
                text={JSON.stringify(context.scopeAmbiguities, null, 2)}
              />
            ) : null}
          </details>
        </InspectorSection>
      ) : null}
      {selectedGroup ? (
        <Modal
          open
          title={selectedGroup.title}
          size="xl"
          onClose={() => setSelectedGroup(null)}
        >
          <MemoryItemsTable items={selectedGroup.items} showScope />
        </Modal>
      ) : null}
    </InspectorStack>
  );
}

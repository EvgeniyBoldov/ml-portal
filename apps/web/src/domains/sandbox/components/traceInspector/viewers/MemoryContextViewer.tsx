import { InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
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
  const counts: [string, number][] = [
    ['Факты', context.selectedFacts],
    ['Проекты', context.selectedProjects],
    ['Термины', context.selectedGlossary],
    ['Знания', context.selectedMemoryItems],
  ];
  return (
    <InspectorStack>
      {context.owner ? (
        <InspectorTextBlock
          text={
            context.owner.kind === 'planner'
              ? 'Собственная накопленная память планера'
              : `Собственная накопленная память задания ${context.owner.id}`
          }
        />
      ) : null}
      <div className={styles.summary}>
        <InspectorStatus
          label={context.fallback ? 'Fallback без памяти' : context.scopeCandidates ? 'Результат поиска' : 'Подготовлен'}
          tone={context.fallback ? 'warn' : 'success'}
        />
        {counts
          .filter(([, count]) => count > 0)
          .map(([label, count]) => (
            <span key={label} className={styles.count}>
              {label}: <strong>{count}</strong>
            </span>
          ))}
      </div>
      {context.scopeCandidates ? <InspectorSection title={`Кандидаты области${context.truncated ? ' · список сокращён' : ''}`}>
        <InspectorTextBlock text={JSON.stringify(context.scopeCandidates, null, 2)} />
      </InspectorSection> : null}
      {context.scopeAmbiguities?.length ? <InspectorSection title="Неоднозначность области">
        <InspectorTextBlock text={JSON.stringify(context.scopeAmbiguities, null, 2)} />
      </InspectorSection> : null}
      {groups
        .filter(group => group.items.length > 0 || group.status)
        .map(group => (
          <InspectorSection
            key={group.title}
            title={`${group.title} · ${group.items.length}`}
          >
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
        <InspectorSection title="Область поиска">
          <InspectorTextBlock
            text={JSON.stringify(context.searchScope, null, 2)}
          />
        </InspectorSection>
      ) : null}
    </InspectorStack>
  );
}

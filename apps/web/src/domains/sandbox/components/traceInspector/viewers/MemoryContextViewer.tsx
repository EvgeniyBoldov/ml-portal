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
  }[] = [
    {
      title: 'Факты пользователя',
      items: context.context.filter(
        item => item.type === 'fact' && item.scope === 'user'
      ),
    },
    {
      title: 'Факты тенанта',
      items: context.context.filter(
        item => item.type === 'fact' && item.scope === 'tenant'
      ),
    },
    {
      title: 'Глоссарий',
      items: context.context.filter(item => item.type === 'glossary'),
    },
    {
      title: 'Долговременная память',
      items: context.context.filter(item => item.type === 'knowledge'),
    },
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
      <div className={styles.summary}>
        <InspectorStatus
          label={context.fallback ? 'Fallback без памяти' : 'Подготовлен'}
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
      {groups
        .filter(group => group.items.length > 0)
        .map(group => (
          <InspectorSection
            key={group.title}
            title={`${group.title} · ${group.items.length}`}
          >
            <MemoryItemsTable items={group.items} showScope={group.showScope} />
          </InspectorSection>
        ))}
      {!context.context.length ? (
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

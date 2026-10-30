import React, { useEffect, useState } from 'react';

import { useChatContext, useResetChatContext } from '@/shared/api/hooks/useChats';
import { Button, ConfirmDialog, Icon, Modal } from '@/shared/ui';

import { ChatMemoryScopes } from './ChatMemoryScopes';
import styles from './ChatContextPanel.module.css';

type ContextItem = Record<string, unknown>;

function textFrom(item: ContextItem | null | undefined, fields: string[]): string | null {
  if (!item) return null;
  for (const field of fields) {
    const value = item[field];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number') return String(value);
    if (Array.isArray(value)) {
      const parts = value.filter((part): part is string | number => typeof part === 'string' || typeof part === 'number');
      if (parts.length) return parts.join(', ');
    }
  }
  return null;
}

function ContextList({ title, items, fields }: {
  title: string;
  items: ContextItem[];
  fields: Array<{ label: string; keys: string[] }>;
}) {
  if (!items.length) return null;

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeading}>
        <h3>{title}</h3>
        <span className={styles.count}>{items.length}</span>
      </div>
      <ul className={styles.list}>
        {items.map((item, index) => (
          <li className={styles.listItem} key={`${title}-${index}`}>
            {fields.map(({ label, keys }, fieldIndex) => {
              const value = textFrom(item, keys);
              if (!value) return null;
              return fieldIndex === 0 ? (
                <p className={styles.itemPrimary} key={label}>{value}</p>
              ) : (
                <p className={styles.itemMeta} key={label}>
                  <span>{label}</span>{value}
                </p>
              );
            })}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ChatContextPanel({ chatId }: { chatId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isConfirmingReset, setIsConfirmingReset] = useState(false);
  const contextQuery = useChatContext(chatId, isOpen);
  const resetMutation = useResetChatContext();
  const context = contextQuery.data;
  const hasAdditionalContextItems = !!context && (
    !!context.recent_anchor ||
    context.term_bindings.length > 0 ||
    context.artifacts.length > 0 ||
    context.open_loops.length > 0 ||
    context.decisions.length > 0 ||
    context.task_results.length > 0
  );

  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const handleReset = async () => {
    await resetMutation.mutateAsync(chatId);
    setIsConfirmingReset(false);
  };

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(true)}
        aria-label="Открыть рабочий контекст чата"
      >
        <Icon name="clipboard-list" size={16} />
        Контекст
      </Button>
      <Modal
        open={isOpen}
        title="Рабочий контекст чата"
        onClose={() => setIsOpen(false)}
        size="lg"
        className={styles.dialog}
        bodyClassName={styles.dialogBody}
        footer={(
          <>
            <Button variant="outline" onClick={() => setIsOpen(false)}>Закрыть</Button>
            <Button
              variant="danger"
              onClick={() => { setIsOpen(false); setIsConfirmingReset(true); }}
              disabled={resetMutation.isPending}
            >
              Сбросить контекст
            </Button>
          </>
        )}
      >
        <div className={styles.content}>
          <div className={styles.intro}>
            <p className={styles.description}>
              Краткая рабочая память чата. История сообщений и сохранённые факты сюда не входят.
            </p>
            {context && <span className={styles.revision}>Версия {context.revision}</span>}
          </div>
          {contextQuery.isLoading ? <p className={styles.empty}>Загрузка рабочего контекста…</p> : null}
          {contextQuery.isError ? (
            <div className={styles.error} role="alert">
              <span>Не удалось обновить рабочий контекст.</span>
              <Button variant="outline" size="sm" onClick={() => { void contextQuery.refetch(); }}>
                Повторить
              </Button>
            </div>
          ) : null}
          {context ? (
            <>
              <section className={styles.section}>
                <div className={styles.sectionHeading}><h3>Текущая цель</h3></div>
                <p className={styles.value}>{textFrom(context.active_goal, ['text', 'status']) ?? 'Нет активной цели'}</p>
              </section>
              <section className={`${styles.section} ${styles.focusSection}`}>
                <div className={styles.sectionHeading}><h3>Фокус</h3></div>
                {textFrom(context.focus, ['topic']) && <p className={styles.value}>{textFrom(context.focus, ['topic'])}</p>}
                <div className={styles.scopeSettings}>
                  <h4>Область поиска</h4>
                  <ChatMemoryScopes key={chatId} chatId={chatId} context={context} />
                </div>
              </section>
              {!hasAdditionalContextItems ? (
                <p className={styles.emptyState}>Дополнительные заметки и результаты пока не сохранены.</p>
              ) : (
                <>
                  <ContextList title="Термины" items={context.term_bindings} fields={[{ label: 'Термин', keys: ['term'] }, { label: 'Также', keys: ['aliases'] }]} />
                  <ContextList title="Файлы" items={context.artifacts} fields={[{ label: 'Файл', keys: ['file_name'] }, { label: 'Роль', keys: ['role'] }]} />
                  <ContextList title="Открытые вопросы" items={context.open_loops} fields={[{ label: 'Вопрос', keys: ['user_message'] }, { label: 'Статус', keys: ['status'] }, { label: 'Причина', keys: ['reason_code'] }]} />
                  <ContextList title="Решения" items={context.decisions} fields={[{ label: 'Решение', keys: ['summary', 'text', 'decision'] }]} />
                  {context.recent_anchor && (
                    <section className={styles.section}>
                      <div className={styles.sectionHeading}><h3>Последний ориентир</h3></div>
                      <p className={styles.value}>{textFrom(context.recent_anchor, ['user_intent', 'assistant_outcome', 'terminal_state']) ?? 'Нет данных'}</p>
                    </section>
                  )}
                  <ContextList title="Результаты задач" items={context.task_results} fields={[{ label: 'Результат', keys: ['safe_summary', 'outcome'] }]} />
                </>
              )}
            </>
          ) : null}
        </div>
      </Modal>
      <ConfirmDialog
        open={isConfirmingReset}
        title="Сбросить рабочий контекст?"
        description="Будут забыты цель, закреплённые файлы, открытые вопросы и краткие результаты задач этого чата. История сообщений и сохранённые факты останутся без изменений."
        confirmLabel="Сбросить"
        cancelLabel="Отмена"
        confirmLoading={resetMutation.isPending}
        onConfirm={() => { void handleReset(); }}
        onCancel={() => { setIsConfirmingReset(false); setIsOpen(true); }}
      />
    </>
  );
}

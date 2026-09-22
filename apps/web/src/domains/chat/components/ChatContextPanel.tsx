import React, { useEffect, useState } from 'react';

import { useChatContext, useResetChatContext } from '@/shared/api/hooks/useChats';
import { Button, ConfirmDialog, Icon, Modal } from '@/shared/ui';

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

function ContextList({ title, items, fields, emptyText }: {
  title: string;
  items: ContextItem[];
  fields: string[];
  emptyText: string;
}) {
  return (
    <section className={styles.section}>
      <h3>{title}</h3>
      {items.length ? (
        <ul className={styles.list}>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>{textFrom(item, fields) ?? 'Нет данных'}</li>
          ))}
        </ul>
      ) : <p className={styles.empty}>{emptyText}</p>}
    </section>
  );
}

export function ChatContextPanel({ chatId }: { chatId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isConfirmingReset, setIsConfirmingReset] = useState(false);
  const contextQuery = useChatContext(chatId, isOpen);
  const resetMutation = useResetChatContext();
  const context = contextQuery.data;

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
          <p className={styles.description}>
            Это краткая рабочая память текущего чата. История сообщений и сохранённые факты сюда не входят.
          </p>
          {contextQuery.isLoading ? <p className={styles.empty}>Загрузка…</p> : null}
          {contextQuery.isError ? <p className={styles.error}>Не удалось загрузить рабочий контекст.</p> : null}
          {context ? (
            <>
              <p className={styles.revision}>Версия контекста: {context.revision}</p>
              <section className={styles.section}>
                <h3>Текущая цель</h3>
                <p className={styles.value}>{textFrom(context.active_goal, ['text', 'status']) ?? 'Нет активной цели'}</p>
              </section>
              <section className={styles.section}>
                <h3>Фокус</h3>
                <p className={styles.value}>{textFrom(context.focus, ['topic', 'project_keys', 'entity_refs']) ?? 'Не задан'}</p>
              </section>
              <ContextList title="Термины" items={context.term_bindings} fields={['term', 'aliases']} emptyText="Термины не закреплены." />
              <ContextList title="Файлы" items={context.artifacts} fields={['file_name', 'role']} emptyText="Файлы не закреплены." />
              <ContextList title="Открытые вопросы" items={context.open_loops} fields={['user_message', 'reason_code', 'status']} emptyText="Нет открытых вопросов." />
              <ContextList title="Решения" items={context.decisions} fields={['text', 'summary', 'decision']} emptyText="Решения не сохранены." />
              <section className={styles.section}>
                <h3>Последний ориентир</h3>
                <p className={styles.value}>{textFrom(context.recent_anchor, ['user_intent', 'assistant_outcome', 'terminal_state']) ?? 'Нет данных'}</p>
              </section>
              <ContextList title="Результаты задач" items={context.task_results} fields={['safe_summary', 'outcome']} emptyText="Результаты задач отсутствуют." />
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

import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/shared/api/http';
import { qk } from '@/shared/api/keys';
import type { ChatContextInspection } from '@/shared/api/chats';
import Button from '@/shared/ui/Button';
import { MemoryScopePicker } from '@/shared/ui/MemoryScopePicker/MemoryScopePicker';

import styles from './ChatMemoryScopes.module.css';

function scopeKeysFrom(context: ChatContextInspection): string[] {
  const keys = context.focus.scope_keys;
  return Array.isArray(keys)
    ? keys.filter((key): key is string => typeof key === 'string')
    : [];
}

export function ChatMemoryScopes({
  chatId,
  context,
}: {
  chatId: string;
  context: ChatContextInspection;
}) {
  const [selected, setSelected] = useState<string[]>(() => scopeKeysFrom(context));
  const [isCatalogReady, setIsCatalogReady] = useState(false);
  const queryClient = useQueryClient();
  useEffect(() => {
    setSelected(scopeKeysFrom(context));
  }, [chatId, context.revision]);
  const save = useMutation({
    mutationFn: (keys: string[] | null) =>
      apiRequest<ChatContextInspection>(`/chats/${chatId}/memory-scopes`, {
        method: 'PUT',
        body: JSON.stringify({
          scope_keys: keys,
          expected_revision: context.revision,
        }),
      }),
    onSuccess: result =>
      queryClient.setQueryData(qk.chats.context(chatId), result),
  });
  const savedKeys = scopeKeysFrom(context);
  const hasSelectionChanged = selected.length !== savedKeys.length ||
    selected.some(key => !savedKeys.includes(key));
  const isInheriting = context.focus.scope_mode !== 'replace';

  return (
    <div className={styles.container}>
      <MemoryScopePicker
        value={selected}
        onChange={setSelected}
        embedded
        disabled={save.isPending}
        onCatalogReadyChange={setIsCatalogReady}
        description={
          context.focus.scope_mode === 'replace'
            ? 'Для этого чата задан отдельный набор проектов.'
            : 'Сейчас используются проекты профиля и рабочей группы. Измените выбор, чтобы задать отдельный набор для этого чата.'
        }
      />
      <div className={styles.actions}>
        <Button
          className={styles.actionButton}
          loading={save.isPending && Array.isArray(save.variables)}
          disabled={save.isPending || !isCatalogReady || !hasSelectionChanged}
          onClick={() => save.mutate(selected)}
        >
          Применить выбор
        </Button>
        <Button
          className={styles.actionButton}
          variant="outline"
          loading={save.isPending && save.variables === null}
          disabled={save.isPending || isInheriting}
          onClick={() => save.mutate(null)}
        >
          Вернуть настройки профиля
        </Button>
      </div>
      <p className={styles.actionHint}>
        Сброс снимет отдельный выбор чата и снова подключит проекты профиля и рабочей группы.
      </p>
      {save.isError && (
        <p className={styles.feedbackError} role="alert">
          Не удалось сохранить выбор. Повторите попытку.
        </p>
      )}
      {save.isSuccess && !hasSelectionChanged && (
        <p className={styles.feedbackSuccess} role="status">
          Настройки области поиска сохранены.
        </p>
      )}
    </div>
  );
}

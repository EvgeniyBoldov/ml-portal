import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/shared/api/http';
import { qk } from '@/shared/api/keys';
import type { ChatContextInspection } from '@/shared/api/chats';
import Button from '@/shared/ui/Button';
import { MemoryScopePicker } from '@/shared/ui/MemoryScopePicker/MemoryScopePicker';

export function ChatMemoryScopes({
  chatId,
  context,
}: {
  chatId: string;
  context: ChatContextInspection;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const queryClient = useQueryClient();
  useEffect(() => {
    const keys = context.focus.scope_keys;
    setSelected(
      Array.isArray(keys)
        ? keys.filter((key): key is string => typeof key === 'string')
        : []
    );
  }, [chatId, context]);
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
  return (
    <>
      <MemoryScopePicker
        value={selected}
        onChange={setSelected}
        disabled={save.isPending}
        description={
          context.focus.scope_mode === 'replace'
            ? 'В этом чате используется собственный выбор проектов.'
            : 'Используются проекты тенанта и пользователя. Выбор ниже заменит весь набор для этого чата.'
        }
      />
      <Button disabled={save.isPending} onClick={() => save.mutate(selected)}>
        Применить к чату
      </Button>
      <Button
        variant="ghost"
        disabled={save.isPending}
        onClick={() => save.mutate(null)}
      >
        Использовать настройки профиля
      </Button>
      {save.isError && (
        <p role="alert">
          Не удалось сохранить проекты. Обновите контекст и повторите выбор.
        </p>
      )}
    </>
  );
}

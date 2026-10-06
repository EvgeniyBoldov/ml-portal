import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/shared/api/http';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import { MemoryScopePicker } from '@/shared/ui/MemoryScopePicker/MemoryScopePicker';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

export function ProfileMemoryScopes({
  scopeKeys,
  tenantScopeKeys,
}: {
  scopeKeys: string[];
  tenantScopeKeys: string[];
}) {
  const [selected, setSelected] = useState(scopeKeys);
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  useEffect(() => setSelected(scopeKeys), [scopeKeys]);
  const save = useMutation({
    mutationFn: () =>
      apiRequest('/profile/memory-scopes', {
        method: 'PUT',
        body: JSON.stringify({ memory_scope_keys: selected }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.profile.all() });
      void queryClient.invalidateQueries({ queryKey: qk.chats.all() });
      showSuccess('Скоупы сохранены');
    },
    onError: (error: Error) => showError(error.message),
  });
  const hasChanges =
    [...selected].sort().join('|') !== [...scopeKeys].sort().join('|');
  return (
    <>
      <MemoryScopePicker
        value={selected}
        onChange={setSelected}
        disabled={save.isPending}
        inheritedKeys={tenantScopeKeys}
        description="Выберите команды и проекты для контекста чатов. Если ветка не выбрана, она наследуется из tenant-а. Явный выбор в чате имеет приоритет."
      />
      <Button
        onClick={() => save.mutate()}
        disabled={!hasChanges || save.isPending}
      >
        {save.isPending ? 'Сохранение…' : 'Сохранить скоупы'}
      </Button>
    </>
  );
}

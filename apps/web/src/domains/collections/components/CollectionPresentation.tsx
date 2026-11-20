import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { collectionsApi } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import { Select } from '@/shared/ui/Select';
import styles from './CollectionPresentation.module.css';

export function useCollectionWorkspace() {
  const [params, setParams] = useSearchParams();
  const tenantId = params.get('tenant_id') || '';
  const workspaces = useQuery({
    queryKey: qk.collections.workspaces(),
    queryFn: collectionsApi.listWorkspaces,
    staleTime: 30_000,
  });
  const isSelected =
    !!tenantId && !!workspaces.data?.items.some(item => item.id === tenantId);
  return {
    tenantId,
    isSelected,
    workspaces,
    select: (id: string) => {
      const next = new URLSearchParams(params);
      if (id) next.set('tenant_id', id);
      else next.delete('tenant_id');
      next.delete('tab');
      setParams(next);
    },
  };
}
export function CollectionWorkspacePicker({
  workspace,
}: {
  workspace: ReturnType<typeof useCollectionWorkspace>;
}) {
  if (workspace.workspaces.isLoading)
    return <p role="status">Загрузка рабочих групп…</p>;
  if (workspace.workspaces.isError)
    return (
      <div role="alert">
        Не удалось загрузить рабочие группы.{' '}
        <Button
          variant="ghost"
          onClick={() => void workspace.workspaces.refetch()}
        >
          Повторить
        </Button>
      </div>
    );
  if (!workspace.workspaces.data?.items.length)
    return <p>Доступных рабочих групп нет.</p>;
  return (
    <div className={styles.workspace}>
      <label htmlFor="collections-workspace">Рабочая группа</label>
      <Select
        id="collections-workspace"
        value={workspace.isSelected ? workspace.tenantId : ''}
        options={[
          { value: '', label: 'Выберите рабочую группу' },
          ...workspace.workspaces.data.items.map(item => ({
            value: item.id,
            label: item.name,
          })),
        ]}
        onChange={workspace.select}
      />
      {!workspace.isSelected && (
        <p className={styles.hint}>
          {workspace.tenantId
            ? 'Выбранная рабочая группа недоступна. Выберите другую.'
            : 'Выберите рабочую группу, чтобы увидеть доступные коллекции.'}
        </p>
      )}
    </div>
  );
}

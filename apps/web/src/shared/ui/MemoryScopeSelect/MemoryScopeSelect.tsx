import { useQuery } from '@tanstack/react-query';
import { memoryScopesApi } from '@/shared/api/memoryScopes';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import MultiSelectTagPicker from '@/shared/ui/MultiSelectTagPicker/MultiSelectTagPicker';

type Props = {
  value: string[];
  onChange: (keys: string[]) => void;
  disabled?: boolean;
  readOnly?: boolean;
  lockedKeys?: string[];
};

export function MemoryScopeSelect({ value, onChange, disabled, readOnly, lockedKeys = [] }: Props) {
  const catalog = useQuery({
    queryKey: qk.memory.scopeCatalog(),
    queryFn: memoryScopesApi.list,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
  });
  const scopes = (catalog.data ?? []).filter(scope => scope.scope_type === 'project');
  const selectedScopes = value.map(key => scopes.find(scope => scope.key === key));
  const missing = value.filter((_, index) => !selectedScopes[index]);
  const options = [
    ...scopes.map(scope => ({
      value: scope.key,
      label: scope.name,
      search: `${scope.key} ${scope.aliases.join(' ')}`,
    })),
    ...missing.map(key => ({ value: key, label: `Недоступный скоуп · ${key}`, search: key })),
  ];

  if (catalog.isLoading) return <span role="status">Загрузка скоупов…</span>;
  if (catalog.isError) return <span role="alert">Не удалось загрузить скоупы. <Button variant="ghost" size="sm" onClick={() => void catalog.refetch()}>Повторить</Button></span>;
  if (readOnly) return <span>{value.map((key, index) => selectedScopes[index]?.name ?? key).join(', ') || 'Не выбраны'}</span>;

  return <MultiSelectTagPicker
    label="Скоупы памяти чатов"
    hideLabel
    options={options}
    value={value}
    lockedValues={lockedKeys}
    disabled={disabled}
    onChange={onChange}
  />;
}

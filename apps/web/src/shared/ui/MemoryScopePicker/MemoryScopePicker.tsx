import React from 'react';
import { useQuery } from '@tanstack/react-query';

import { collectionsApi } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import Checkbox from '@/shared/ui/Checkbox';
import Button from '@/shared/ui/Button';

import styles from './MemoryScopePicker.module.css';

interface MemoryScopePickerProps {
  value: string[];
  onChange: (keys: string[]) => void;
  disabled?: boolean;
  readOnly?: boolean;
  description?: string;
  inheritedKeys?: string[];
}

export function MemoryScopePicker({
  value,
  onChange,
  disabled,
  readOnly,
  description,
  inheritedKeys = [],
}: MemoryScopePickerProps) {
  const catalog = useQuery({
    queryKey: qk.collections.memoryScopeCatalog(),
    queryFn: collectionsApi.getMemoryScopeCatalog,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
  });
  const scopes = (catalog.data ?? []).filter(scope => !scope.is_all);
  const handleChange = (key: string, checked: boolean) => {
    onChange(
      checked ? [...value, key] : value.filter(selected => selected !== key)
    );
  };

  return (
    <section className={styles.panel}>
      <h2 className={styles.title}>Скоупы для чатов</h2>
      {description && <p className={styles.hint}>{description}</p>}
      {catalog.isLoading && <p role="status">Загрузка областей…</p>}
      {catalog.isError && (
        <p role="alert">
          Не удалось загрузить области.{' '}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void catalog.refetch()}
          >
            Повторить
          </Button>
        </p>
      )}
      {catalog.data && (
        <div className={styles.branches}>
          {(['team', 'project'] as const).map(branch => {
            const options = scopes.filter(scope => scope.scope_type === branch);
            const selected = value.filter(key => key.startsWith(`${branch}.`));
            const inherited = selected.length
              ? []
              : options.filter(scope => inheritedKeys.includes(scope.key));
            const unknown = selected.filter(
              key => !options.some(scope => scope.key === key)
            );
            return (
              <fieldset key={branch} className={styles.branch}>
                <legend>{branch === 'team' ? 'Команды' : 'Проекты'}</legend>
                {readOnly ? (
                  <p>
                    {selected.length
                      ? selected
                          .map(
                            key =>
                              options.find(scope => scope.key === key)?.name ??
                              key
                          )
                          .join(', ')
                      : 'Не выбраны'}
                  </p>
                ) : (
                  <>
                    {options.map(scope => (
                      <Checkbox
                        key={scope.key}
                        label={scope.name}
                        checked={value.includes(scope.key)}
                        disabled={disabled}
                        onChange={checked => handleChange(scope.key, checked)}
                      />
                    ))}
                    {unknown.map(key => (
                      <Checkbox
                        key={key}
                        label={key}
                        description="Область больше недоступна — снимите выбор"
                        checked
                        disabled={disabled}
                        onChange={checked => handleChange(key, checked)}
                      />
                    ))}
                    {!options.length && (
                      <p className={styles.hint}>Нет доступных областей</p>
                    )}
                  </>
                )}
                {inherited.length > 0 && (
                  <p className={styles.hint}>
                    Из tenant-а: {inherited.map(scope => scope.name).join(', ')}
                  </p>
                )}
              </fieldset>
            );
          })}
        </div>
      )}
    </section>
  );
}

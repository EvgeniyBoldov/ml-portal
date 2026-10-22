import React from 'react';
import { useQuery } from '@tanstack/react-query';

import { memoryScopesApi } from '@/shared/api/memoryScopes';
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
    queryKey: qk.memory.scopeCatalog(),
    queryFn: memoryScopesApi.list,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
  });
  const scopes = catalog.data ?? [];
  const unknown = value.filter(key => !scopes.some(scope => scope.key === key));
  return (
    <section className={styles.panel}>
      <h2 className={styles.title}>Проекты для памяти чатов</h2>
      {description && <p className={styles.hint}>{description}</p>}
      {catalog.isLoading && <p role="status">Загрузка проектов…</p>}
      {catalog.isError && (
        <p role="alert">
          Не удалось загрузить проекты.{' '}
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
        <fieldset className={styles.branch}>
          <legend>Проекты</legend>
          {readOnly ? (
            <p>
              {value
                .map(key => scopes.find(scope => scope.key === key)?.name ?? key)
                .join(', ') || 'Не выбраны'}
            </p>
          ) : (
            <>
              {scopes.map(scope => (
                <Checkbox
                  key={scope.key}
                  label={`${scope.name} (${scope.key})`}
                  checked={value.includes(scope.key)}
                  disabled={disabled}
                  onChange={checked =>
                    onChange(
                      checked
                        ? [...value, scope.key]
                        : value.filter(key => key !== scope.key)
                    )
                  }
                />
              ))}
              {unknown.map(key => (
                <Checkbox
                  key={key}
                  label={key}
                  checked
                  disabled={disabled}
                  description="Проект больше недоступен — снимите выбор"
                  onChange={() => onChange(value.filter(selected => selected !== key))}
                />
              ))}
              {!scopes.length && <p className={styles.hint}>Нет доступных проектов</p>}
            </>
          )}
          {inheritedKeys.length > 0 && (
            <p className={styles.hint}>
              Проекты тенанта:{' '}
              {inheritedKeys
                .map(
                  key => scopes.find(scope => scope.key === key)?.name ?? key
                )
                .join(', ')}
            </p>
          )}
        </fieldset>
      )}
    </section>
  );
}

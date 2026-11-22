import { useId, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@/shared/api/admin';
import { agentsApi } from '@/shared/api/agents';
import { collectionsApi } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import type { ResourceType } from '@/shared/api/rbac';
import { tenantApi } from '@/shared/api/tenant';
import { Button, Input, Select } from '@/shared/ui';
import { resourceOptions } from './accessRules';
import styles from './AccessFields.module.css';

export interface Choice {
  value: string;
  label: string;
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Choice[];
  disabled?: boolean;
  placeholder?: string;
  labelAction?: ReactNode;
  beforeSelect?: ReactNode;
}

export function AccessSelect({
  label,
  labelAction,
  beforeSelect,
  ...props
}: FieldProps) {
  const id = useId();
  return (
    <div className={styles.field}>
      <div className={styles.labelRow}>
        <label htmlFor={id}>{label}</label>
        {labelAction}
      </div>
      {beforeSelect}
      <Select id={id} {...props} />
    </div>
  );
}

interface PickerProps {
  kind: 'user' | 'tenant' | 'agent' | 'instance';
  label: string;
  selected?: Choice;
  onChange: (option: Choice | undefined) => void;
}

function AccessPicker({ kind, label, selected, onChange }: PickerProps) {
  const [search, setSearch] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const query = search.trim();
  const users = useQuery({
    queryKey: qk.admin.users.list({ q: query, limit: 100 }),
    queryFn: () => adminApi.getUsers({ query, limit: 100 }),
    enabled: kind === 'user',
  });
  const tenantParams = { search: query, size: 100 };
  const tenants = useQuery({
    queryKey: qk.admin.tenants.list(tenantParams),
    queryFn: () => tenantApi.getTenants(tenantParams),
    enabled: kind === 'tenant',
  });
  const agents = useQuery({
    queryKey: qk.agents.list({ limit: 1000 }),
    queryFn: () => agentsApi.list({ limit: 1000 }),
    enabled: kind === 'agent',
  });
  const collectionParams = { search: query, size: 100, is_active: true };
  const collections = useQuery({
    queryKey: qk.collections.adminList(collectionParams),
    queryFn: () => collectionsApi.listAll(collectionParams),
    enabled: kind === 'instance',
  });

  const request = {
    user: users,
    tenant: tenants,
    agent: agents,
    instance: collections,
  }[kind];
  const catalogs = {
    user: users.data?.users.map(user => ({
      value: user.id,
      label: user.login,
    })),
    tenant: tenants.data?.items.map(tenant => ({
      value: tenant.id,
      label: tenant.name,
    })),
    agent: agents.data?.map(agent => ({
      value: agent.id,
      label: agent.name || agent.slug,
    })),
    instance: collections.data?.items.map(collection => ({
      value: collection.id,
      label: collection.name || collection.slug,
    })),
  };
  const options = (catalogs[kind] ?? []).filter(
    option =>
      kind !== 'agent' ||
      option.label.toLowerCase().includes(query.toLowerCase())
  );
  if (selected && !options.some(option => option.value === selected.value)) {
    options.unshift(selected);
  }

  return (
    <div className={styles.field}>
      <AccessSelect
        label={label}
        labelAction={
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={`Поиск · ${label}`}
            aria-expanded={showSearch}
            className={styles.searchToggle}
            onClick={() => {
              if (showSearch) setSearch('');
              setShowSearch(!showSearch);
            }}
          >
            {showSearch ? 'Скрыть поиск' : 'Найти'}
          </Button>
        }
        beforeSelect={
          showSearch && (
            <Input
              type="search"
              aria-label={`Фильтр по имени · ${label}`}
              placeholder="Введите имя"
              value={search}
              onChange={event => setSearch(event.target.value)}
            />
          )
        }
        value={selected?.value ?? ''}
        onChange={value =>
          onChange(options.find(option => option.value === value))
        }
        options={options}
        disabled={!options.length}
        placeholder={
          request.isPending
            ? 'Загрузка…'
            : options.length
              ? 'Выберите значение'
              : 'Ничего не найдено'
        }
      />
      {request.isError && (
        <div role="alert">
          Не удалось загрузить список.{' '}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => void request.refetch()}
          >
            Повторить
          </Button>
        </div>
      )}
    </div>
  );
}

export function AccessOwnerPicker(
  props: Omit<PickerProps, 'label' | 'kind'> & { kind: 'user' | 'tenant' }
) {
  return (
    <AccessPicker
      {...props}
      key={props.kind}
      label={props.kind === 'user' ? 'Пользователь' : 'Рабочая группа'}
    />
  );
}

interface ResourceFieldsProps {
  type: ResourceType | '';
  setType: (type: ResourceType) => void;
  selected?: Choice;
  onChange: (option: Choice | undefined) => void;
}

export function AccessResourceFields({
  type,
  setType,
  selected,
  onChange,
}: ResourceFieldsProps) {
  return (
    <div className={styles.field}>
      <AccessSelect
        label="Тип ресурса"
        value={type}
        onChange={value => setType(value as ResourceType)}
        options={resourceOptions}
        placeholder="Выберите тип"
      />
      {(type === 'agent' || type === 'instance') && (
        <AccessPicker
          key={type}
          kind={type}
          label={type === 'agent' ? 'Агент' : 'Коллекция'}
          selected={selected}
          onChange={onChange}
        />
      )}
    </div>
  );
}

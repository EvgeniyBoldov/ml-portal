import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import {
  rbacApi,
  type ExplainAccessRequest,
  type ResourceType,
} from '@/shared/api/rbac';
import { Block, Button } from '@/shared/ui';
import {
  AccessOwnerPicker,
  AccessResourceFields,
  type Choice,
} from './AccessFields';
import { AccessExplanation } from './AccessExplanation';
import styles from './AccessCheck.module.css';

export function AccessCheck() {
  const [user, setUser] = useState<Choice>();
  const [type, setType] = useState<ResourceType | ''>('');
  const [resource, setResource] = useState<Choice>();
  const [request, setRequest] = useState<ExplainAccessRequest>();
  const check = useQuery({
    queryKey: qk.rbac.explanation(request ?? {}),
    queryFn: () => rbacApi.explainAccess(request!),
    enabled: !!request,
  });

  return (
    <div className={styles.content}>
      <Block title="Пользователь и ресурс" icon="user" iconVariant="primary">
        <form
          className={styles.form}
          onSubmit={event => {
            event.preventDefault();
            if (!user || !type || !resource) return;
            if (request) void check.refetch();
            else
              setRequest({
                user_id: user.value,
                resource_type: type,
                resource_id: resource.value,
              });
          }}
        >
          <AccessOwnerPicker
            kind="user"
            selected={user}
            onChange={value => {
              setUser(value);
              setRequest(undefined);
            }}
          />
          <AccessResourceFields
            type={type}
            setType={value => {
              setType(value);
              setResource(undefined);
              setRequest(undefined);
            }}
            selected={resource}
            onChange={value => {
              setResource(value);
              setRequest(undefined);
            }}
          />
          <div className={styles.actions}>
            <Button
              type="submit"
              disabled={!user || !resource || !type || check.isFetching}
            >
              {check.isFetching ? 'Проверяем…' : 'Проверить доступ'}
            </Button>
          </div>
        </form>
      </Block>
      {request && check.isError && (
        <p role="alert">Не удалось проверить доступ. Повторите проверку.</p>
      )}
      {request && check.data && <AccessExplanation result={check.data} />}
    </div>
  );
}

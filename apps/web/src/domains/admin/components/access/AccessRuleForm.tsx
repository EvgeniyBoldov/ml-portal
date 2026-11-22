import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import {
  rbacApi,
  type EnrichedRule,
  type RbacEffect,
  type RbacLevel,
  type ResourceType,
} from '@/shared/api/rbac';
import { FormModal } from '@/shared/ui';
import { useSuccessToast } from '@/shared/ui/Toast';
import {
  AccessOwnerPicker,
  AccessResourceFields,
  AccessSelect,
  type Choice,
} from './AccessFields';
import {
  ACCESS_PATH,
  decisionOptions,
  ownerName,
  ownerOptions,
} from './accessRules';
import styles from './AccessRuleForm.module.css';

export function AccessRuleForm({
  rule,
  onClose,
}: {
  rule?: EnrichedRule;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const success = useSuccessToast();
  const [level, setLevel] = useState<RbacLevel | ''>(rule?.owner.level ?? '');
  const [owner, setOwner] = useState<Choice | undefined>(() => {
    const id = rule?.owner.user_id || rule?.owner.tenant_id;
    return rule && id ? { value: id, label: ownerName(rule.owner) } : undefined;
  });
  const [type, setType] = useState<ResourceType | ''>(
    rule?.resource.type ?? ''
  );
  const [resource, setResource] = useState<Choice | undefined>(
    rule && { value: rule.resource.id, label: rule.resource.name }
  );
  const [effect, setEffect] = useState<RbacEffect | ''>(rule?.effect ?? '');

  const scope = {
    level: level || undefined,
    owner_platform: level === 'platform',
    owner_user_id: level === 'user' ? owner?.value : undefined,
    owner_tenant_id: level === 'tenant' ? owner?.value : undefined,
    resource_type: type || undefined,
    resource_id: resource?.value,
  };
  const lookup = { ...scope, include_deprecated: true };
  const hasTarget = Boolean(
    level && (level === 'platform' || owner) && type && resource
  );
  const duplicateQuery = useQuery({
    queryKey: qk.rbac.enrichedRules(lookup),
    queryFn: () => rbacApi.listEnrichedRules(lookup),
    enabled: hasTarget,
  });
  const duplicate = duplicateQuery.data?.find(item => item.id !== rule?.id);
  const save = useMutation({
    mutationFn: () => {
      if (
        !level ||
        !type ||
        !effect ||
        !resource ||
        (level !== 'platform' && !owner)
      ) {
        throw new Error('Заполните поля правила');
      }
      const payload = {
        ...scope,
        level,
        resource_type: type,
        resource_id: resource.value,
        effect,
      };
      return rule
        ? rbacApi.updateRule(rule.id, payload)
        : rbacApi.createRule(payload);
    },
    onSuccess: async saved => {
      await client.invalidateQueries({ queryKey: qk.rbac.all() });
      success(rule ? 'Правило сохранено' : 'Правило создано');
      onClose();
      if (!rule) {
        navigate(`${ACCESS_PATH}/${saved.id}`, {
          state: { search: location.search },
        });
      }
    },
    onError: () => void duplicateQuery.refetch(),
  });

  const close = () => {
    if (!save.isPending) onClose();
  };
  const audience =
    level === 'platform' ? 'всей платформы' : owner && `«${owner.label}»`;
  return (
    <FormModal
      open
      title={rule ? 'Изменить правило' : 'Новое правило доступа'}
      size="md"
      onClose={close}
      onSubmit={() => save.mutate()}
      saving={save.isPending}
      submitDisabled={
        !hasTarget || !effect || !!duplicate || duplicateQuery.isFetching
      }
      submitLabel={rule ? 'Сохранить' : 'Создать правило'}
    >
      <div className={styles.form} aria-busy={save.isPending}>
        <AccessSelect
          label="Для кого"
          value={level}
          placeholder="Выберите уровень"
          options={ownerOptions}
          onChange={value => {
            setLevel(value as RbacLevel);
            setOwner(undefined);
          }}
        />
        {(level === 'user' || level === 'tenant') && (
          <AccessOwnerPicker
            kind={level}
            selected={owner}
            onChange={setOwner}
          />
        )}
        <AccessResourceFields
          type={type}
          setType={value => {
            setType(value);
            setResource(undefined);
          }}
          selected={resource}
          onChange={setResource}
        />
        <AccessSelect
          label="Решение"
          value={effect}
          options={decisionOptions}
          placeholder="Выберите действие"
          onChange={value => setEffect(value as RbacEffect)}
        />
        {hasTarget && effect && resource && (
          <p className={styles.preview} aria-live="polite">
            {effect === 'allow' ? 'Разрешить' : 'Запретить'} доступ к «
            {resource.label}» для {audience}.
          </p>
        )}
        {duplicate && (
          <p role="status" className={styles.preview}>
            Правило для этого адресата и ресурса уже существует.{' '}
            <Link to={`${ACCESS_PATH}/${duplicate.id}`} onClick={close}>
              Открыть правило
            </Link>
          </p>
        )}
        {save.isError && (
          <p role="alert" className={styles.error}>
            {save.error.message}
          </p>
        )}
      </div>
    </FormModal>
  );
}

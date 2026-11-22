import { useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/shared/api/keys';
import { rbacApi, type EnrichedRule } from '@/shared/api/rbac';
import { Block, Button, LifecycleDeleteDialog } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import LifecycleRestoreDialog from '@/shared/ui/LifecycleRestoreDialog';
import { AccessExplanation } from '../components/access/AccessExplanation';
import {
  AccessDecisionBadge,
  AccessStatusBadge,
} from '../components/access/AccessRuleBadges';
import { AccessRuleForm } from '../components/access/AccessRuleForm';
import {
  accessBreadcrumb,
  isEditable,
  ownerName,
  resourceTypeName,
} from '../components/access/accessRules';
import { RBAC_LEVEL_LABELS } from '../shared/rbacLabels';
import styles from './AccessRulePage.module.css';

function Inheritance({ rule }: { rule: EnrichedRule }) {
  const request = {
    user_id: rule.owner.user_id ?? undefined,
    tenant_id: rule.owner.user_id
      ? undefined
      : (rule.owner.tenant_id ?? undefined),
    resource_type: rule.resource.type,
    resource_id: rule.resource.id,
  };
  const check = useQuery({
    queryKey: qk.rbac.explanation(request),
    queryFn: () => rbacApi.explainAccess(request),
  });
  if (check.isPending) return <p role="status">Загрузка решения…</p>;
  if (check.isError) {
    return (
      <p role="alert">
        Не удалось загрузить наследование.{' '}
        <Button variant="ghost" onClick={() => void check.refetch()}>
          Повторить
        </Button>
      </p>
    );
  }
  return <AccessExplanation result={check.data} currentRuleId={rule.id} />;
}

export function AccessRulePage() {
  const { id = '' } = useParams();
  return <AccessRuleDetail key={id} id={id} />;
}

function AccessRuleDetail({ id }: { id: string }) {
  const location = useLocation();
  const search = new URLSearchParams(location.state?.search ?? '');
  const query = search.get('q');
  const parent = {
    ...accessBreadcrumb,
    href: query
      ? `${accessBreadcrumb.href}?${new URLSearchParams({ q: query })}`
      : accessBreadcrumb.href,
  };
  const client = useQueryClient();
  const [dialog, setDialog] = useState<'edit' | 'delete' | 'restore'>();
  const detail = useQuery({
    queryKey: qk.rbac.enrichedDetail(id),
    queryFn: () => rbacApi.getEnrichedRule(id),
  });
  const rule = detail.data;
  const close = () => setDialog(undefined);
  const onLifecycleSuccess = () => {
    void client.invalidateQueries({ queryKey: qk.rbac.all() });
    close();
  };
  const archived = rule?.lifecycle_status === 'deprecated';
  const actions = rule
    ? [
        ...(isEditable(rule.resource.type) && !archived
          ? [
              <Button key="edit" onClick={() => setDialog('edit')}>
                Изменить
              </Button>,
            ]
          : []),
        archived ? (
          <Button
            key="restore"
            variant="outline"
            onClick={() => setDialog('restore')}
          >
            Восстановить
          </Button>
        ) : (
          <Button
            key="delete"
            variant="ghost"
            onClick={() => setDialog('delete')}
          >
            Удалить правило
          </Button>
        ),
      ]
    : [];

  return (
    <>
      <EntityPageV2
        title={rule?.resource.name || 'Правило доступа'}
        subtitle={
          rule
            ? `${resourceTypeName(rule.resource.type)} · ${ownerName(rule.owner)}`
            : undefined
        }
        breadcrumbs={[parent, { label: 'Правило' }]}
        mode="view"
        loading={detail.isPending}
        actionButtons={actions}
      >
        <Tab title="Обзор" layout="full">
          {detail.isError && (
            <p role="alert">
              Не удалось загрузить правило.{' '}
              <Button variant="ghost" onClick={() => void detail.refetch()}>
                Повторить
              </Button>
            </p>
          )}
          {rule && (
            <div className={styles.overview}>
              <Block
                title="Правило доступа"
                icon="shield"
                iconVariant="primary"
              >
                <dl className={styles.facts}>
                  <div>
                    <dt>Для кого</dt>
                    <dd>{ownerName(rule.owner)}</dd>
                  </div>
                  <div>
                    <dt>Уровень</dt>
                    <dd>{RBAC_LEVEL_LABELS[rule.owner.level]}</dd>
                  </div>
                  <div>
                    <dt>Решение правила</dt>
                    <dd>
                      <AccessDecisionBadge effect={rule.effect} />
                    </dd>
                  </div>
                  <div>
                    <dt>Статус</dt>
                    <dd>
                      <AccessStatusBadge rule={rule} />
                    </dd>
                  </div>
                </dl>
              </Block>
              <Block title="Сведения" icon="file-text" iconVariant="neutral">
                <dl className={styles.facts}>
                  <div>
                    <dt>Создал</dt>
                    <dd>{rule.created_by_name || '—'}</dd>
                  </div>
                  <div>
                    <dt>Создано</dt>
                    <dd>{new Date(rule.created_at).toLocaleString('ru-RU')}</dd>
                  </div>
                </dl>
              </Block>
            </div>
          )}
        </Tab>
        <Tab title="Наследование" layout="full" hidden={!rule}>
          {rule && <Inheritance rule={rule} />}
        </Tab>
      </EntityPageV2>
      {rule && dialog === 'edit' && (
        <AccessRuleForm rule={rule} onClose={close} />
      )}
      {rule && dialog === 'delete' && (
        <LifecycleDeleteDialog
          open
          kind="rbac_rule"
          entityId={id}
          entityLabel={rule.resource.name}
          onCancel={close}
          onSuccess={onLifecycleSuccess}
        />
      )}
      {rule && dialog === 'restore' && (
        <LifecycleRestoreDialog
          open
          kind="rbac_rule"
          entityId={id}
          entityLabel={rule.resource.name}
          onCancel={close}
          onSuccess={onLifecycleSuccess}
        />
      )}
    </>
  );
}

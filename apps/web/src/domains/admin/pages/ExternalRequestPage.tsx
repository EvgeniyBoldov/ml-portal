import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { ApiError } from '@/shared/api/errors';
import {
  getExternalRequest,
  type ExternalRequestDetail,
} from '@/shared/api/externalRequests';
import { qk } from '@/shared/api/keys';
import { Alert, Badge, Button } from '@/shared/ui';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { Block } from '@/shared/ui/GridLayout';

import { runStatusLabel, runStatusTone } from './agentRunStatus';
import styles from './ExternalRequestPage.module.css';
import { duration, ExternalRequestTimeline } from './ExternalRequestTimeline';

const externalRequestsPath = '/admin/agent-runs?tab=external-requests';

function RequestDetails({
  request,
  refreshedAt,
}: {
  request: ExternalRequestDetail;
  refreshedAt: number;
}) {
  return (
    <>
      <Block
        title="Ход поручения"
        icon="activity"
        iconVariant="primary"
        width="2/3"
        className={styles['overview-block']}
        headerActions={
          <div role="status">
            <Badge tone={runStatusTone(request.status)}>
              {runStatusLabel[request.status] ?? request.status}
            </Badge>
          </div>
        }
      >
        <ExternalRequestTimeline request={request} />
      </Block>
      <Block
        title="Сведения о запросе"
        icon="file-text"
        iconVariant="info"
        width="1/3"
        className={styles['overview-block']}
        fields={[
          { key: 'source', type: 'text', label: 'Источник' },
          { key: 'created_at', type: 'date', label: 'Принято' },
          request.completed_at
            ? { key: 'completed_at', type: 'date', label: 'Завершено' }
            : { key: 'updated_at', type: 'date', label: 'Обновлено' },
          {
            key: 'duration',
            type: 'text',
            label: request.completed_at ? 'Длительность' : 'Прошло с принятия',
          },
        ]}
        data={{
          ...request,
          duration: duration(
            request.created_at,
            request.completed_at ?? refreshedAt
          ),
        }}
      />
    </>
  );
}

export default function ExternalRequestPage() {
  const { id = '' } = useParams();
  const { data, dataUpdatedAt, error, isLoading, isFetching, refetch } =
    useQuery({
      queryKey: qk.admin.externalRequest(id),
      queryFn: () => getExternalRequest(id),
      enabled: Boolean(id),
      retry: (count, failure) =>
        count < 1 && (!(failure instanceof ApiError) || failure.status >= 500),
      refetchInterval: query => {
        const request = query.state.data;
        return request &&
          (!request.completed_at ||
            request.timeline.some(
              step =>
                step.delivery_status === 'pending' ||
                step.delivery_status === 'sending'
            ))
          ? 15_000
          : false;
      },
    });
  const isNotFound = error instanceof ApiError && error.status === 404;

  return (
    <EntityPageV2
      title="Поручение"
      subtitle={id}
      mode="view"
      loading={isLoading}
      breadcrumbs={[
        { label: 'Внешние запросы', href: externalRequestsPath },
        { label: 'Поручение' },
      ]}
    >
      <Tab title="Обзор" id="overview" layout="grid">
        {error && (
          <Alert
            className={styles['full-width']}
            variant={isNotFound ? 'neutral' : 'danger'}
            title={
              isNotFound
                ? 'Поручение не найдено'
                : data
                  ? 'Не удалось обновить поручение'
                  : 'Не удалось загрузить поручение'
            }
          >
            {!isNotFound && (
              <Button
                size="sm"
                variant="outline"
                loading={isFetching}
                onClick={() => void refetch()}
              >
                Повторить
              </Button>
            )}
          </Alert>
        )}
        {data && !isNotFound && (
          <RequestDetails request={data} refreshedAt={dataUpdatedAt} />
        )}
      </Tab>
    </EntityPageV2>
  );
}

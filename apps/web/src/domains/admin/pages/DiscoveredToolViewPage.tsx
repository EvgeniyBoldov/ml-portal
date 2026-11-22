import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useParams } from 'react-router-dom';

import {
  discoveredToolsApi,
  type DiscoveredToolDetail,
  type DiscoveredToolUpdateRequest,
} from '@/shared/api/discoveredTools';
import { qk } from '@/shared/api/keys';
import { Alert, Button, EntityPageV2, Tab } from '@/shared/ui';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import {
  ToolOrigin,
  ToolSchemas,
  ToolSettingsBlock,
  type ToolSettings,
} from '../components/tools/ToolDetailsBlocks';
import { TOOLS_PATH } from '../shared/toolCatalog';
import styles from './DiscoveredToolViewPage.module.css';

function ToolDetail({
  tool,
  listPath,
}: {
  tool: DiscoveredToolDetail;
  listPath: string;
}) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<{
    base: ToolSettings;
    changes: ToolSettings;
  }>();
  const update = useMutation({
    mutationFn: (changes: DiscoveredToolUpdateRequest) =>
      discoveredToolsApi.update(tool.id, changes),
    onSuccess: updated => {
      client.setQueryData(qk.discoveredTools.detail(tool.id), updated);
      void client.invalidateQueries({ queryKey: qk.discoveredTools.all() });
      setDraft(undefined);
    },
  });
  const mode = draft ? 'edit' : 'view';

  function handleSave() {
    if (!draft || update.isPending) return;
    const changes: DiscoveredToolUpdateRequest = {};
    if (draft.changes.risk_level !== draft.base.risk_level) {
      changes.risk_level = draft.changes.risk_level;
    }
    if (draft.changes.result_delivery !== draft.base.result_delivery) {
      changes.result_delivery = draft.changes.result_delivery;
    }

    if (Object.keys(changes).length) update.mutate(changes);
    else setDraft(undefined);
  }

  const actions = tool.runtime_managed
    ? []
    : buildEntityCrudActions({
        mode,
        saving: update.isPending,
        labels: { edit: 'Изменить настройки' },
        onEdit: () => {
          const base = {
            risk_level: tool.risk_level,
            result_delivery: tool.result_delivery,
          };
          update.reset();
          setDraft({ base, changes: base });
        },
        onCancel: () => {
          if (update.isPending) return;
          setDraft(undefined);
          update.reset();
        },
        onSave: handleSave,
      });
  const errorNotice = update.isError && (
    <Alert
      className={styles.notice}
      variant="danger"
      title="Не удалось сохранить настройки инструмента"
      description="Изменения остались в форме. Попробуйте сохранить снова."
    />
  );

  return (
    <EntityPageV2
      title={tool.name}
      subtitle={tool.name !== tool.slug ? tool.slug : undefined}
      mode={mode}
      breadcrumbs={[
        { label: 'Инструменты', href: listPath },
        { label: tool.name },
      ]}
    >
      <Tab title="Обзор" layout="grid" id="overview" actions={actions}>
        {errorNotice}
        <ToolOrigin tool={tool} />
        <ToolSettingsBlock
          tool={tool}
          changes={draft?.changes}
          saving={update.isPending}
          onRiskChange={risk_level =>
            setDraft(
              current =>
                current && {
                  ...current,
                  changes: { ...current.changes, risk_level },
                }
            )
          }
          onDeliveryChange={result_delivery =>
            setDraft(
              current =>
                current && {
                  ...current,
                  changes: { ...current.changes, result_delivery },
                }
            )
          }
        />
      </Tab>
      <Tab
        title="Схемы"
        layout="grid"
        id="schemas"
        actions={draft ? actions : []}
      >
        {errorNotice}
        <ToolSchemas tool={tool} />
      </Tab>
    </EntityPageV2>
  );
}

export function DiscoveredToolViewPage() {
  const { id = '' } = useParams();
  const { search } = useLocation();
  const listPath = `${TOOLS_PATH}${search}`;
  const detail = useQuery({
    queryKey: qk.discoveredTools.detail(id),
    queryFn: () => discoveredToolsApi.get(id),
    enabled: Boolean(id),
    staleTime: 30_000,
  });

  if (detail.data) {
    return <ToolDetail key={id} tool={detail.data} listPath={listPath} />;
  }

  return (
    <EntityPageV2
      title="Инструмент"
      mode="view"
      breadcrumbs={[
        { label: 'Инструменты', href: listPath },
        { label: 'Карточка' },
      ]}
      loading={detail.isPending}
    >
      <Tab title="Обзор" layout="full">
        <Alert variant="danger" title="Не удалось загрузить инструмент">
          <Button variant="outline" onClick={() => void detail.refetch()}>
            Повторить
          </Button>
        </Alert>
      </Tab>
    </EntityPageV2>
  );
}

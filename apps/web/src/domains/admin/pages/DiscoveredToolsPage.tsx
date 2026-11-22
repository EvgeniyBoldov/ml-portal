import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';

import {
  discoveredToolsApi,
  type DiscoveredToolListItem,
} from '@/shared/api/discoveredTools';
import { qk } from '@/shared/api/keys';
import { toolInstancesApi } from '@/shared/api/toolInstances';
import {
  Alert,
  Button,
  ConfirmDialog,
  EntityPageV2,
  Input,
  Tab,
  type DataTableFilterValue,
} from '@/shared/ui';
import { BUILTIN_PROVIDER, providerName } from '../shared/toolCatalog';
import { useToast } from '@/shared/ui/Toast';
import { ToolRegistryTable } from '../components/tools/ToolRegistryTable';
import styles from './DiscoveredToolsPage.module.css';

const columnFilterKeys = ['provider', 'type', 'risk', 'delivery'] as const;

export function DiscoveredToolsPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [confirmScan, setConfirmScan] = useState(false);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const registry = useQuery({
    queryKey: qk.discoveredTools.list({}),
    queryFn: () => discoveredToolsApi.list(),
    refetchOnMount: 'always',
    staleTime: 30_000,
  });

  const tools = registry.data ?? [];
  const providers = new Map<string, DiscoveredToolListItem>();
  for (const tool of tools) {
    providers.set(tool.provider_instance_id ?? BUILTIN_PROVIDER, tool);
  }
  const providerOptions = [...providers.entries()]
    .map(([value, tool]) => ({
      value,
      label: providerName(tool),
    }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ru'));

  const search = params.get('q') ?? '';
  const provider = params.get('provider') ?? '';
  const columnFilters = Object.fromEntries(
    columnFilterKeys.map(key => [key, params.get(key)])
  );
  const selectedProvider = providers.get(provider);
  const providerDetail = useQuery({
    queryKey: qk.toolInstances.detail(provider),
    queryFn: () => toolInstancesApi.get(provider),
    enabled:
      registry.isSuccess &&
      /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(provider) &&
      !selectedProvider,
    retry: false,
  });
  const scopedProvider =
    selectedProvider?.source === 'mcp'
      ? {
          id: selectedProvider.provider_instance_id,
          name: providerName(selectedProvider),
        }
      : providerDetail.data?.connector_type === 'mcp' && !selectedProvider
        ? providerDetail.data
        : undefined;
  if (provider && !selectedProvider) {
    providerOptions.push({
      value: provider,
      label: providerDetail.data?.name ?? 'Выбранный провайдер',
    });
  }

  const rescan = useMutation({
    mutationFn: () =>
      discoveredToolsApi.rescan({
        include_local: !scopedProvider,
        provider_instance_id: scopedProvider?.id,
      }),
    onError: () => showToast('Не удалось выполнить сканирование', 'error'),
    onSuccess: async ({ stats }) => {
      const failed = stats.mcp_failed_providers ?? [];
      if (stats.skipped) {
        showToast('Сканирование уже выполняется', 'info');
      } else if (failed.length) {
        showToast(
          `Не удалось опросить: ${failed.map(item => item.provider_slug).join(', ')}.`,
          'warning'
        );
      } else {
        const count =
          (stats.local_upserted ?? 0) +
          (stats.system_upserted ?? 0) +
          (stats.mcp_upserted ?? 0);
        showToast(
          `Сканирование завершено. Найдено или обновлено: ${count}.`,
          'success'
        );
      }
      setPage(1);
      await queryClient.invalidateQueries({
        queryKey: qk.discoveredTools.all(),
      });
    },
  });

  function setFilter(key: string, value: string) {
    setPage(1);
    setParams(
      previous => {
        if (value) previous.set(key, value);
        else previous.delete(key);
        return previous;
      },
      { replace: true }
    );
  }

  function setColumnFilters(filters: Record<string, DataTableFilterValue>) {
    setPage(1);
    setParams(
      previous => {
        if (Object.keys(filters).length === 0) previous.delete('q');
        for (const key of columnFilterKeys) {
          const value = filters[key];
          if (typeof value === 'string' && value) previous.set(key, value);
          else previous.delete(key);
        }
        return previous;
      },
      { replace: true }
    );
  }

  return (
    <>
      <EntityPageV2
        title="Инструменты"
        mode="view"
        breadcrumbs={[{ label: 'Инструменты' }]}
      >
        <Tab
          title="Реестр"
          layout="full"
          actions={[
            <div className={styles.headerControls} key="controls">
              <Input
                className={styles.search}
                type="search"
                aria-label="Поиск инструментов"
                placeholder="Имя, slug или провайдер"
                value={search}
                onChange={event => setFilter('q', event.target.value)}
              />
              <Button
                loading={rescan.isPending}
                disabled={Boolean(
                  provider && !selectedProvider && !providerDetail.data
                )}
                onClick={() => setConfirmScan(true)}
              >
                Сканировать источники
              </Button>
            </div>,
          ]}
        >
          <div className={styles.registry}>
            {providerDetail.isError && !selectedProvider && (
              <Alert
                variant="warning"
                title="Выбранный провайдер недоступен"
                description="Сбросьте фильтр, чтобы вернуться к общему реестру."
              />
            )}
            {registry.isError ? (
              <Alert variant="danger" title="Не удалось загрузить инструменты">
                <Button
                  variant="outline"
                  onClick={() => void registry.refetch()}
                >
                  Повторить
                </Button>
              </Alert>
            ) : (
              <ToolRegistryTable
                tools={tools}
                providerOptions={providerOptions}
                columnFilters={columnFilters}
                onColumnFiltersChange={setColumnFilters}
                loading={registry.isPending}
                search={search}
                paginated={tools.length > 25}
                page={page}
                onPageChange={setPage}
              />
            )}
          </div>
        </Tab>
      </EntityPageV2>
      <ConfirmDialog
        open={confirmScan}
        title={
          scopedProvider
            ? 'Сканировать провайдер?'
            : 'Сканировать все источники?'
        }
        message={
          <>
            <p>
              {scopedProvider
                ? `Будет опрошен только «${scopedProvider.name}».`
                : 'Будут опрошены локальные инструменты и все активные MCP-провайдеры.'}
            </p>
            <p>
              Записи, которые не удастся обнаружить, могут исчезнуть из реестра.
            </p>
          </>
        }
        confirmLabel="Сканировать"
        cancelLabel="Отмена"
        variant="warning"
        onConfirm={() => {
          setConfirmScan(false);
          rescan.mutate();
        }}
        onCancel={() => setConfirmScan(false)}
      />
    </>
  );
}

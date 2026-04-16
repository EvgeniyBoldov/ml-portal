/**
 * SessionSidebar — left panel with navigation, overrides and runs list.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Badge from '@/shared/ui/Badge';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxBranchListItem, SandboxRunListItem, SandboxSelectedItem, SandboxSessionDetail } from '../types';
import { useCatalogData } from '../hooks/useSandboxNavigation';
import { formatSandboxDomainLabel, formatSandboxDomainTone } from '../shared/domainLabels';
import AccordionSection from './AccordionSection';
import styles from './SessionSidebar.module.css';

interface Props {
  sessionId: string;
  session: SandboxSessionDetail;
  branches: SandboxBranchListItem[];
  activeBranchId: string;
  runs: SandboxRunListItem[];
  activeRunId: string | null;
  selectedItem: SandboxSelectedItem | null;
  onSelectBranch: (branchId: string) => void;
  onSelectItem: (item: SandboxSelectedItem) => void;
}

const TYPE_LABELS: Record<string, string> = {
  agent_version: 'Агент',
  discovered_tool: 'Инструмент',
  orchestration: 'Оркестрация',
  policy: 'Политика',
  limit: 'Лимит',
  model: 'Модель',
};

const STATUS_TONE: Record<string, 'success' | 'neutral' | 'warn' | 'danger'> = {
  running: 'warn',
  completed: 'success',
  failed: 'danger',
  waiting_confirmation: 'warn',
};

export default function SessionSidebar({
  sessionId,
  session,
  branches,
  activeBranchId,
  runs,
  activeRunId,
  selectedItem,
  onSelectBranch,
  onSelectItem,
}: Props) {
  const { data: catalog, isLoading: isCatalogLoading, isOrchestratorsLoading } = useCatalogData(sessionId);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const toolById = useMemo(
    () => new Map(catalog.tools.map((tool) => [tool.id, tool])),
    [catalog.tools],
  );
  const agentVersionLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of catalog.agents) {
      for (const version of agent.versions) {
        map.set(version.id, `${agent.name} v${version.version}`);
      }
    }
    return map;
  }, [catalog.agents]);

  const { data: branchOverrides = [] } = useQuery({
    queryKey: qk.sandbox.branchOverrides.list(sessionId, activeBranchId),
    queryFn: () => sandboxApi.listBranchOverrides(sessionId, activeBranchId),
    enabled: activeBranchId.length > 0,
    staleTime: 15_000,
  });

  const hasOverrideForEntity = (entityType: string, entityId: string | null): boolean =>
    branchOverrides.some((override) => override.entity_type === entityType && (override.entity_id ?? null) === entityId);

  const hasOverrideForParameter = (parameterTab: 'platform'): boolean =>
    branchOverrides.some(
      (override) =>
        override.entity_type === 'orchestration' &&
        override.entity_id === null &&
        override.field_path.startsWith(`${parameterTab}.`),
    );

  const resolveToolPublished = (toolId: string, defaultPublished: boolean): boolean => {
    const override = branchOverrides.find(
      (item) =>
        item.entity_type === 'discovered_tool' &&
        (item.entity_id ?? null) === toolId &&
        item.field_path === 'published',
    );
    if (!override) {
      return defaultPublished;
    }
    return Boolean(override.value_json);
  };

  const resolveOverrideTitle = (override: typeof branchOverrides[number]): string => {
    const entityTypeLabel = TYPE_LABELS[override.entity_type] ?? override.entity_type;
    if (!override.entity_id) {
      return entityTypeLabel;
    }
    if (override.entity_type === 'discovered_tool') {
      const tool = toolById.get(override.entity_id);
      return `${entityTypeLabel}${tool ? ` (${tool.name || tool.slug})` : ''}`;
    }
    if (override.entity_type === 'agent_version') {
      const agentLabel = agentVersionLabelById.get(override.entity_id);
      return `${entityTypeLabel}${agentLabel ? ` (${agentLabel})` : ''}`;
    }
    return entityTypeLabel;
  };

  const groupedOverrides = branchOverrides.reduce<Record<string, { key: string; title: string; fields: string[] }>>((acc, override) => {
    const entityKey = `${override.entity_type}:${override.entity_id ?? 'global'}`;
    if (!acc[entityKey]) {
      acc[entityKey] = {
        key: entityKey,
        title: resolveOverrideTitle(override),
        fields: [],
      };
    }
    acc[entityKey].fields.push(override.field_path);
    return acc;
  }, {});

  const groupedOverridesList = Object.values(groupedOverrides);

  const normalizedDomainGroups = catalog.domain_groups.map((group) => ({
    ...group,
    tools: [...group.tools].sort((a, b) => a.name.localeCompare(b.name, 'ru')),
  }));

  const isDomainExpanded = (domainId: string): boolean =>
    expandedGroups[domainId] ?? false;

  const toggleDomain = (domainId: string): void => {
    setExpandedGroups((prev) => ({
      ...prev,
      [domainId]: !(prev[domainId] ?? false),
    }));
  };

  const isAgentSelected = (agentId: string): boolean =>
    selectedItem?.type === 'agent' && selectedItem.id === agentId;

  const isAgentVersionSelected = (agentId: string, versionId: string): boolean =>
    selectedItem?.type === 'agent' &&
    selectedItem.id === agentId &&
    (selectedItem.versionId ?? null) === versionId;

  const isToolSelected = (toolId: string): boolean =>
    selectedItem?.type === 'tool' && selectedItem.id === toolId;

  const isToolVersionSelected = (toolId: string, versionId: string): boolean =>
    selectedItem?.type === 'tool' &&
    selectedItem.id === toolId &&
    (selectedItem.versionId ?? null) === versionId;

  return (
    <div className={styles.sidebar}>
      <AccordionSection title="Оркестраторы" count={catalog.system_routers.length}>
        {isCatalogLoading || isOrchestratorsLoading ? (
          <div className={styles['empty-section']}>Загрузка...</div>
        ) : catalog.system_routers.length === 0 ? (
          <div className={styles['empty-section']}>Нет доступных оркестраторов</div>
        ) : (
          <div className={styles['nav-list']}>
            {catalog.system_routers.map((router) => (
              <button
                type="button"
                key={router.id}
                className={`${styles['nav-item']} ${
                  selectedItem?.type === 'router' && selectedItem.id === router.id
                    ? styles['nav-item-active']
                    : ''
                }`}
                onClick={() =>
                  onSelectItem({ type: 'router', id: router.id, name: router.name })
                }
              >
                <span className={styles['nav-name']}>
                  {router.name}
                  {hasOverrideForEntity('orchestration', router.id) ? <span className={styles['override-dot']} /> : null}
                </span>
                <span className={styles['nav-desc']}>{router.description}</span>
              </button>
            ))}
          </div>
        )}
      </AccordionSection>

      <AccordionSection title="Агенты" count={catalog.agents.length}>
        {isCatalogLoading ? (
          <div className={styles['empty-section']}>Загрузка...</div>
        ) : catalog.agents.length === 0 ? (
          <div className={styles['empty-section']}>Нет доступных агентов</div>
        ) : (
          <div className={styles['nav-list']}>
            {catalog.agents.map((agent) => (
              <div key={agent.id} className={styles['tool-domain-item']}>
                <button
                  type="button"
                  className={`${styles['nav-item']} ${
                    isAgentSelected(agent.id) ? styles['nav-item-active'] : ''
                  }`}
                  onClick={() =>
                    onSelectItem({ type: 'agent', id: agent.id, name: agent.name })
                  }
                >
                  <span className={styles['nav-name']}>
                    {agent.name}
                    {agent.versions.some((version) => hasOverrideForEntity('agent_version', version.id)) ? (
                      <span className={styles['override-dot']} />
                    ) : null}
                  </span>
                  <span className={styles['nav-slug']}>{agent.slug}</span>
                </button>
                {agent.versions.length > 0 ? (
                  <div className={styles['tool-version-list']}>
                    {agent.versions.map((version) => (
                      <button
                        type="button"
                        key={version.id}
                        className={`${styles['version-item-btn']} ${
                          isAgentVersionSelected(agent.id, version.id) ? styles['version-item-active'] : ''
                        }`}
                        onClick={() =>
                          onSelectItem({
                            type: 'agent',
                            id: agent.id,
                            name: `${agent.name} v${version.version}`,
                            versionId: version.id,
                          })
                        }
                      >
                        <span className={styles['version-item-label']}>
                          v{version.version}
                          {hasOverrideForEntity('agent_version', version.id) ? (
                            <span className={styles['override-dot']} />
                          ) : null}
                        </span>
                        <span className={styles['version-item-status']}>{version.status}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </AccordionSection>

      <AccordionSection title="Инструменты" count={normalizedDomainGroups.length}>
        {isCatalogLoading ? (
          <div className={styles['empty-section']}>Загрузка...</div>
        ) : normalizedDomainGroups.length === 0 ? (
          <div className={styles['empty-section']}>Нет доступных инструментов</div>
        ) : (
          <div className={styles['tool-domain-list']}>
            {normalizedDomainGroups.map((group) => {
              const groupId = group.domain;
              const isExpanded = isDomainExpanded(groupId);
              return (
                <div key={group.domain} className={styles['tool-domain-group']}>
                  <button
                    type="button"
                    className={styles['group-header']}
                    onClick={() => toggleDomain(groupId)}
                    aria-expanded={isExpanded}
                  >
                    <span className={styles['group-name']}>
                      {formatSandboxDomainLabel(group.domain)}
                      <Badge tone={formatSandboxDomainTone(group.domain)}>{group.tools.length}</Badge>
                    </span>
                    <span
                      className={`${styles['group-toggle']} ${isExpanded ? styles.expanded : ''}`}
                    >
                      ▾
                    </span>
                  </button>
                  {isExpanded ? (
                    <div className={styles['tool-domain-items']}>
                      {group.tools.map((tool) => (
                        <div key={tool.id} className={styles['tool-domain-item']}>
                          <button
                            type="button"
                            className={`${styles['nav-item']} ${
                              isToolSelected(tool.id) ? styles['nav-item-active'] : ''
                            }`}
                            onClick={() =>
                              onSelectItem({ type: 'tool', id: tool.id, name: tool.name })
                            }
                          >
                            <span className={styles['nav-name']}>
                              {tool.name}
                            </span>
                            <span className={styles['nav-slug']}>{tool.slug}</span>
                            <span className={styles['nav-desc']}>
                              <Badge tone={resolveToolPublished(tool.id, tool.published) ? 'success' : 'warn'}>
                                {resolveToolPublished(tool.id, tool.published) ? 'Опубликован' : 'Черновик'}
                              </Badge>
                              <span>{tool.source}</span>
                              {tool.domains.length > 1 ? (
                                <span>
                                  {tool.domains.slice(1).map(formatSandboxDomainLabel).join(' · ')}
                                </span>
                              ) : null}
                            </span>
                          </button>
                          {tool.versions.length > 0 ? (
                            <div className={styles['tool-version-list']}>
                              {tool.versions.map((version) => (
                                <button
                                  type="button"
                                  key={version.id}
                                  className={`${styles['version-item-btn']} ${
                                    isToolVersionSelected(tool.id, version.id) ? styles['version-item-active'] : ''
                                  }`}
                                  onClick={() =>
                                    onSelectItem({
                                      type: 'tool',
                                      id: tool.id,
                                      name: `${tool.name} v${version.version}`,
                                      versionId: version.id,
                                    })
                                  }
                                >
                                  <span className={styles['version-item-label']}>v{version.version}</span>
                                  <span className={styles['version-item-status']}>{version.status}</span>
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </AccordionSection>

      <AccordionSection title="Параметры" count={1}>
        <div className={styles['nav-list']}>
          <button
            type="button"
            className={`${styles['nav-item']} ${
              selectedItem?.type === 'parameter' && selectedItem.id === 'platform'
                ? styles['nav-item-active']
                : ''
            }`}
            onClick={() => onSelectItem({ type: 'parameter', id: 'platform', name: 'Платформа' })}
          >
            <span className={styles['nav-name']}>
              Платформа
              {hasOverrideForParameter('platform') ? <span className={styles['override-dot']} /> : null}
            </span>
          </button>
        </div>
      </AccordionSection>

      <AccordionSection title="Оверрайды" count={branchOverrides.length}>
        {groupedOverridesList.length === 0 ? (
          <div className={styles['empty-section']}>Нет оверрайдов</div>
        ) : (
          <div className={styles['override-list']}>
            {groupedOverridesList.map((group) => (
              <div key={group.key} className={styles['override-item']}>
                <div className={styles['override-label']}>
                  <span className={styles['active-dot']} />
                  <span className={styles['override-name']}>{group.title}</span>
                </div>
                <span className={styles['override-type']}>
                  {group.fields.length} полей
                </span>
              </div>
            ))}
          </div>
        )}
      </AccordionSection>

      <AccordionSection title="Запуски" count={runs.length}>
        {branches.length === 0 ? (
          <div className={styles['empty-section']}>Нет веток</div>
        ) : (
          <div className={styles['branch-run-tree']}>
            {branches.map((branch) => {
              const isBranchActive = branch.id === activeBranchId;
              const branchRuns = runs.filter((run) => run.branch_id === branch.id);
              return (
                <div key={branch.id} className={styles['branch-run-group']}>
                  <button
                    type="button"
                    className={`${styles['branch-run-title']} ${isBranchActive ? styles['branch-run-title-active'] : ''}`}
                    onClick={() => onSelectBranch(branch.id)}
                  >
                    {branch.name}
                  </button>
                  {isBranchActive && (
                    <div className={styles['run-list']}>
                      {branchRuns.length === 0 ? (
                        <div className={styles['empty-section']}>Нет запусков в ветке</div>
                      ) : (
                        branchRuns.map((r) => (
                          <div
                            key={r.id}
                            className={`${styles['run-item']} ${
                              r.id === activeRunId ? styles['run-item-active'] : ''
                            }`}
                          >
                            <span className={styles['run-text']}>
                              {r.request_text.slice(0, 60)}
                              {r.request_text.length > 60 ? '...' : ''}
                            </span>
                            <div className={styles['run-meta']}>
                              <Badge tone={STATUS_TONE[r.status] ?? 'neutral'}>
                                {r.status}
                              </Badge>
                              <span>{r.steps_count} шагов</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </AccordionSection>

    </div>
  );
}

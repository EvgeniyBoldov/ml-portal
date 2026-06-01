/**
 * SessionSidebar — left panel with navigation, overrides and runs list.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Badge from '@/shared/ui/Badge';
import Button from '@/shared/ui/Button';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import { qk } from '@/shared/api/keys';
import { sandboxApi } from '../api';
import type { SandboxBranchListItem, SandboxSelectedItem, SandboxSessionDetail } from '../types';
import { useCatalogData } from '../hooks/useSandboxNavigation';
import { formatSandboxDomainLabel, formatSandboxDomainTone } from '../shared/domainLabels';
import AccordionSection from './AccordionSection';
import styles from './SessionSidebar.module.css';

interface Props {
  sessionId: string;
  session: SandboxSessionDetail;
  branches: SandboxBranchListItem[];
  activeBranchId: string;
  selectedItem: SandboxSelectedItem | null;
  onSelectBranch: (branchId: string) => void;
  onSelectItem: (item: SandboxSelectedItem) => void;
  onCreateBranch: () => void;
  onClearBranchOverrides: () => void;
  isClearingOverrides?: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  agent_version: 'Агент',
  discovered_tool: 'Инструмент',
  orchestration: 'Оркестратор',
  policy: 'Политика',
  limit: 'Лимит',
  model: 'Модель',
};

function isPlatformOverrideFieldPath(fieldPath: string): boolean {
  return fieldPath.startsWith('platform.') || fieldPath.startsWith('platform_limits.');
}

function getOverrideGroupKey(override: { entity_type: string; entity_id: string | null; field_path: string }): string {
  if (override.entity_type === 'orchestration' && override.entity_id === null) {
    if (isPlatformOverrideFieldPath(override.field_path)) return 'orchestration:global:platform';
    if (override.field_path === 'agent.version_id') return 'orchestration:global:agent_version_pin';
  }
  return `${override.entity_type}:${override.entity_id ?? 'global'}`;
}

function toVersionStateLabel(versionStatus: string, isCurrent: boolean): string {
  if (isCurrent) return 'Текущая';
  if (versionStatus === 'published' || versionStatus === 'active') return 'Опубликована';
  return 'Неактивная';
}

export default function SessionSidebar({
  sessionId,
  session,
  branches,
  activeBranchId,
  selectedItem,
  onSelectBranch,
  onSelectItem,
  onCreateBranch,
  onClearBranchOverrides,
  isClearingOverrides = false,
}: Props) {
  const { data: catalog, isLoading: isCatalogLoading, isOrchestratorsLoading } = useCatalogData(sessionId);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [showClearOverridesModal, setShowClearOverridesModal] = useState(false);

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
  const { data: branchArtifacts } = useQuery({
    queryKey: qk.sandbox.branchArtifacts.meta(sessionId, activeBranchId),
    queryFn: () => sandboxApi.getBranchArtifactsMeta(sessionId, activeBranchId),
    enabled: activeBranchId.length > 0,
    staleTime: 15_000,
  });

  const hasOverrideForEntity = (entityType: string, entityId: string | null): boolean =>
    branchOverrides.some((override) => override.entity_type === entityType && (override.entity_id ?? null) === entityId);

  const countOverridesForEntity = (entityType: string, entityId: string | null): number =>
    branchOverrides.filter((override) => override.entity_type === entityType && (override.entity_id ?? null) === entityId).length;

  const hasOverrideForParameter = (parameterTab: 'platform'): boolean => {
    if (parameterTab !== 'platform') return false;
    return branchOverrides.some(
      (override) =>
        override.entity_type === 'orchestration' &&
        override.entity_id === null &&
        isPlatformOverrideFieldPath(override.field_path),
    );
  };

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

  const groupedOverrides = branchOverrides.reduce<Record<string, { key: string; title: string; fields: string[]; entityType: string; entityId: string | null }>>((acc, override) => {
    const entityKey = getOverrideGroupKey(override);
    if (!acc[entityKey]) {
      acc[entityKey] = {
        key: entityKey,
        title: resolveOverrideTitle(override),
        fields: [],
        entityType: override.entity_type,
        entityId: override.entity_id ?? null,
      };
    }
    acc[entityKey].fields.push(override.field_path);
    return acc;
  }, {});

  const groupedOverridesList = Object.values(groupedOverrides);

  const resolveOverrideSelection = (groupKey: string): SandboxSelectedItem | null => {
    const items = branchOverrides.filter((item) => getOverrideGroupKey(item) === groupKey);
    if (items.length === 0) return null;

    const first = items[0];
    if (first.entity_type === 'agent_version') {
      const targetVersionId = first.entity_id;
      if (!targetVersionId) return null;
      for (const agent of catalog.agents) {
        const version = agent.versions.find((v) => v.id === targetVersionId);
        if (version) {
          return {
            type: 'agent',
            id: agent.id,
            name: `${agent.name} v${version.version}`,
            versionId: version.id,
          };
        }
      }
      return null;
    }

    if (first.entity_type === 'discovered_tool') {
      if (!first.entity_id) return null;
      const tool = catalog.tools.find((t) => t.id === first.entity_id);
      if (!tool) return null;
      const releaseOverride = items.find((item) => item.field_path === 'tool_release_id');
      const releaseId = typeof releaseOverride?.value_json === 'string' ? releaseOverride.value_json : null;
      return {
        type: 'tool',
        id: tool.id,
        name: releaseId ? `${tool.name}` : tool.name,
        versionId: releaseId,
      };
    }

    if (first.entity_type === 'orchestration') {
      const versionOverride = items.find((item) => item.field_path === 'agent.version_id');
      if (versionOverride && typeof versionOverride.value_json === 'string') {
        const targetVersionId = versionOverride.value_json;
        for (const agent of catalog.agents) {
          const version = agent.versions.find((v) => v.id === targetVersionId);
          if (version) {
            return {
              type: 'agent',
              id: agent.id,
              name: `${agent.name} v${version.version}`,
              versionId: version.id,
            };
          }
        }
      }
      if (first.entity_id) {
        const router = catalog.system_routers.find(
          (item) => item.id === first.entity_id,
        );
        if (router) {
          return { type: 'router', id: router.id, name: router.name };
        }
      }
      if (groupKey === 'orchestration:global:platform') {
        return { type: 'parameter', id: 'platform', name: 'Платформа' };
      }
      return null;
    }

    return null;
  };

  const isOverrideGroupSelected = (groupKey: string): boolean => {
    const target = resolveOverrideSelection(groupKey);
    if (!target || !selectedItem) return false;
    if (target.type !== selectedItem.type) return false;
    if (target.id !== selectedItem.id) return false;
    if ((target.versionId ?? null) !== (selectedItem.versionId ?? null)) return false;
    return true;
  };

  const overrideGroupMeta = (group: { key: string; title: string; fields: string[]; entityType: string; entityId: string | null }) => {
    const target = resolveOverrideSelection(group.key);
    const typeLabel = TYPE_LABELS[group.entityType] ?? group.entityType;

    if (group.key === 'orchestration:global:agent_version_pin' && group.fields.includes('agent.version_id')) {
      let versionFlow: string | null = null;
      let agentName = '—';
      if (target?.type === 'agent' && target.versionId) {
        const agent = catalog.agents.find((item) => item.id === target.id);
        agentName = agent?.name ?? agentName;
        const targetVersion = agent?.versions.find((item) => item.id === target.versionId);
        const currentVersion = agent?.versions.find((item) => item.id === agent.current_version_id);
        if (currentVersion && targetVersion) {
          versionFlow = `v${currentVersion.version}->v${targetVersion.version}`;
        } else if (targetVersion) {
          versionFlow = `v${targetVersion.version}`;
        }
      }
      return {
        typeLabel: 'Агент',
        nameLabel: agentName,
        versionLabel: versionFlow,
      };
    }

    if (group.key === 'orchestration:global:platform') {
      return {
        typeLabel: 'Параметры',
        nameLabel: 'Платформа',
        versionLabel: null,
      };
    }

    if (target?.type === 'agent' && target.versionId) {
      const agent = catalog.agents.find((item) => item.id === target.id);
      const version = agent?.versions.find((item) => item.id === target.versionId);
      return {
        typeLabel,
        nameLabel: agent?.name ?? group.title,
        versionLabel: version ? `v${version.version}` : '—',
      };
    }

    if (target?.type === 'tool') {
      const tool = catalog.tools.find((item) => item.id === target.id);
      const version = tool?.versions.find((item) => item.id === (target.versionId ?? ''));
      return {
        typeLabel,
        nameLabel: tool?.name ?? group.title,
        versionLabel: version ? `v${version.version}` : '—',
      };
    }

    if (target?.type === 'router') {
      return {
        typeLabel: 'Оркестратор',
        nameLabel: target.name,
        versionLabel: null,
      };
    }

    return {
      typeLabel,
      nameLabel: group.title,
      versionLabel: null,
    };
  };

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

  const activeBranchAgentVersionId = (() => {
    const item = branchOverrides.find(
      (override) =>
        override.entity_type === 'orchestration' &&
        override.entity_id === null &&
        override.field_path === 'agent.version_id',
    );
    return typeof item?.value_json === 'string' ? item.value_json : null;
  })();

  const activeBranchAgentId = useMemo(() => {
    if (!activeBranchAgentVersionId) return null;
    for (const agent of catalog.agents) {
      if (agent.versions.some((version) => version.id === activeBranchAgentVersionId)) {
        return agent.id;
      }
    }
    return null;
  }, [activeBranchAgentVersionId, catalog.agents]);

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
                          <span className={styles['version-left-mark']}>
                            {activeBranchAgentVersionId && activeBranchAgentId === agent.id
                              ? activeBranchAgentVersionId === version.id ? '✓' : ''
                              : agent.current_version_id === version.id ? '✓' : ''}
                          </span>
                          v{version.version}
                        </span>
                        <span className={styles['version-item-count']}>
                          {countOverridesForEntity('agent_version', version.id) > 0
                            ? countOverridesForEntity('agent_version', version.id)
                            : ''}
                        </span>
                        <span className={styles['version-item-status']}>
                          {toVersionStateLabel(version.status, agent.current_version_id === version.id)}
                        </span>
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
                              <Badge tone={resolveToolPublished(tool.id, tool.published) ? 'success' : 'neutral'}>
                                {resolveToolPublished(tool.id, tool.published) ? 'Доступен' : 'Без активной версии'}
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
                                  <span className={styles['version-item-status']}>
                                    {toVersionStateLabel(version.status, tool.current_version_id === version.id)}
                                  </span>
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

      <AccordionSection
        title="Оверрайды"
        count={branchOverrides.length}
        actions={
          branchOverrides.length > 0 && activeBranchId ? (
            <button
              type="button"
              className={styles['clear-overrides-btn']}
              onClick={() => setShowClearOverridesModal(true)}
              title="Очистить все оверрайды ветки"
            >
              Очистить
            </button>
          ) : null
        }
      >
        {groupedOverridesList.length === 0 ? (
          <div className={styles['empty-section']}>Нет оверрайдов</div>
        ) : (
          <div className={styles['override-list']}>
            {groupedOverridesList.map((group) => (
              (() => {
                const meta = overrideGroupMeta(group);
                return (
              <button
                type="button"
                key={group.key}
                className={`${styles['override-item']} ${isOverrideGroupSelected(group.key) ? styles['override-item-active'] : ''}`}
                onClick={() => {
                  const target = resolveOverrideSelection(group.key);
                  if (target) onSelectItem(target);
                }}
              >
                <div className={styles['override-main-row']}>
                  <span className={styles['override-type']}>{meta.typeLabel}</span>
                  <span className={styles['override-name']}>
                    {meta.nameLabel}
                  </span>
                </div>
                <div className={styles['override-sub-row']}>
                  {meta.versionLabel ? <span className={styles['override-chip']}>{meta.versionLabel}</span> : null}
                  {group.key !== 'orchestration:global:agent_version_pin' ? (
                    <span className={styles['override-chip']}>{group.fields.length} полей</span>
                  ) : null}
                </div>
              </button>
                );
              })()
            ))}
          </div>
        )}
      </AccordionSection>

      <AccordionSection title="Ветки" count={branches.length}>
        {branches.length === 0 ? (
          <div className={styles['empty-section']}>Нет веток</div>
        ) : (
          <div className={styles['branch-list']}>
            {branches.map((branch) => {
              const isBranchActive = branch.id === activeBranchId;
              return (
                <button
                  key={branch.id}
                  type="button"
                  className={`${styles['branch-item']} ${isBranchActive ? styles['branch-item-active'] : ''}`}
                  onClick={() => onSelectBranch(branch.id)}
                >
                  <span className={styles['branch-name']}>{branch.name}</span>
                  {isBranchActive && <span className={styles['branch-active-mark']}>●</span>}
                </button>
              );
            })}
            <button
              type="button"
              className={styles['branch-add-btn']}
              onClick={onCreateBranch}
              title="Создать новую ветку"
            >
              ＋
            </button>
          </div>
        )}
      </AccordionSection>

      <AccordionSection title="Артефакты" count={2}>
        <div className={styles['nav-list']}>
          <button
            type="button"
            className={`${styles['nav-item']} ${
              selectedItem?.type === 'artifact' && selectedItem.artifactKind === 'facts'
                ? styles['nav-item-active']
                : ''
            }`}
            onClick={() => onSelectItem({ type: 'artifact', id: 'branch-facts', name: 'Факты', artifactKind: 'facts' })}
          >
            <span className={styles['nav-name']}>Факты</span>
            <span className={styles['nav-desc']}>
              {typeof branchArtifacts?.facts_count === 'number' ? `${branchArtifacts.facts_count} шт.` : '—'}
            </span>
          </button>
          <button
            type="button"
            className={`${styles['nav-item']} ${
              selectedItem?.type === 'artifact' && selectedItem.artifactKind === 'summary'
                ? styles['nav-item-active']
                : ''
            }`}
            onClick={() => onSelectItem({ type: 'artifact', id: 'branch-summary', name: 'Саммари', artifactKind: 'summary' })}
          >
            <span className={styles['nav-name']}>Саммари</span>
            <span className={styles['nav-desc']}>
              {branchArtifacts?.summary_present ? 'Есть' : 'Пусто'}
            </span>
          </button>
        </div>
      </AccordionSection>

      <ConfirmDialog
        open={showClearOverridesModal}
        title="Очистить оверрайды"
        message={`Вы уверены, что хотите удалить все ${branchOverrides.length} оверрайдов из текущей ветки?`}
        variant="warning"
        confirmLabel="Очистить"
        cancelLabel="Отмена"
        confirmLoading={isClearingOverrides}
        onConfirm={() => {
          onClearBranchOverrides();
          setShowClearOverridesModal(false);
        }}
        onCancel={() => setShowClearOverridesModal(false)}
      />
    </div>
  );
}

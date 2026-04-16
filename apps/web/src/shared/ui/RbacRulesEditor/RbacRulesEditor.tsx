/**
 * RbacRulesEditor - Reusable component for editing RBAC permissions
 * 
 * Used in:
 * - DefaultsPage (scope: default)
 * - TenantEditorPage (scope: tenant)
 * - UserEditorPage (scope: user)
 */
import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { agentsApi, toolInstancesApi, type ToolInstance } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '../Button';
import Badge from '../Badge';
import styles from './RbacRulesEditor.module.css';

type PermissionValue = 'allowed' | 'denied' | 'undefined';

export interface RbacPermissions {
  instance_permissions: Record<string, PermissionValue>;
  agent_permissions: Record<string, PermissionValue>;
}

interface RbacRulesEditorProps {
  scope: 'default' | 'tenant' | 'user';
  permissions: RbacPermissions;
  onChange: (permissions: RbacPermissions) => void;
  editable?: boolean;
}

type TabType = 'agents' | 'instances';

export function RbacRulesEditor({
  scope,
  permissions,
  onChange,
  editable = true,
}: RbacRulesEditorProps) {
  const [activeTab, setActiveTab] = useState<TabType>('agents');
  const [filter, setFilter] = useState('');

  // Load agents
  const { data: agentsData } = useQuery({
    queryKey: qk.agents.list({}),
    queryFn: () => agentsApi.list(),
  });
  const agents = agentsData || [];

  // Load instances
  const { data: instances = [] } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list(),
  });

  // Filter items
  const filteredAgents = useMemo(() => {
    if (!filter) return agents;
    const lowerFilter = filter.toLowerCase();
    return agents.filter(
      (a: any) =>
        a.slug.toLowerCase().includes(lowerFilter) ||
        a.name.toLowerCase().includes(lowerFilter)
    );
  }, [agents, filter]);

  const filteredInstances = useMemo(() => {
    if (!filter) return instances;
    const lowerFilter = filter.toLowerCase();
    return instances.filter(
      (i: ToolInstance) =>
        i.slug.toLowerCase().includes(lowerFilter) ||
        i.name.toLowerCase().includes(lowerFilter)
    );
  }, [instances, filter]);

  // Get permission value with fallback
  const getAgentPermission = (slug: string): PermissionValue => {
    return permissions.agent_permissions[slug] || 'undefined';
  };

  const getInstancePermission = (slug: string): PermissionValue => {
    return permissions.instance_permissions[slug] || 'undefined';
  };

  // Cycle permission value
  const cyclePermission = (
    type: 'agent' | 'instance',
    slug: string
  ) => {
    const currentPerms = type === 'agent' 
      ? permissions.agent_permissions 
      : permissions.instance_permissions;
    
    const current = currentPerms[slug] || 'undefined';
    
    // For default scope: only allowed/denied
    // For tenant/user scope: allowed/denied/undefined
    let next: PermissionValue;
    if (scope === 'default') {
      next = current === 'allowed' ? 'denied' : 'allowed';
    } else {
      next = current === 'undefined' ? 'allowed' 
           : current === 'allowed' ? 'denied' 
           : 'undefined';
    }

    const newPerms = { ...currentPerms, [slug]: next };
    
    // Remove undefined values (inherit from parent)
    if (next === 'undefined') {
      delete newPerms[slug];
    }

    if (type === 'agent') {
      onChange({ ...permissions, agent_permissions: newPerms });
    } else {
      onChange({ ...permissions, instance_permissions: newPerms });
    }
  };

  // Get badge for permission value
  const getPermissionBadge = (value: PermissionValue) => {
    switch (value) {
      case 'allowed':
        return <Badge tone="success">Разрешён</Badge>;
      case 'denied':
        return <Badge tone="danger">Запрещён</Badge>;
      default:
        return <Badge tone="neutral">Наследуется</Badge>;
    }
  };

  return (
    <div className={styles.container}>
      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'agents' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('agents')}
        >
          Агенты ({agents.length})
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'instances' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('instances')}
        >
          Коннекторы ({instances.length})
        </button>
      </div>

      {/* Filter */}
      <div className={styles.filterRow}>
        <input
          type="text"
          placeholder="Поиск..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className={styles.filterInput}
        />
        {scope !== 'default' && (
          <span className={styles.hint}>
            Клик для переключения: Разрешён → Запрещён → Наследуется
          </span>
        )}
      </div>

      {/* Content */}
      <div className={styles.content}>
        {activeTab === 'agents' && (
          <div className={styles.list}>
            {filteredAgents.length === 0 ? (
              <div className={styles.empty}>Нет агентов</div>
            ) : (
              filteredAgents.map((agent: any) => {
                const perm = getAgentPermission(agent.slug);
                return (
                  <div key={agent.slug} className={styles.item}>
                    <div className={styles.itemInfo}>
                      <span className={styles.itemName}>{agent.name}</span>
                      <span className={styles.itemSlug}>{agent.slug}</span>
                    </div>
                    <div className={styles.itemAction}>
                      {editable ? (
                        <Button
                          variant="ghost"
                          size="small"
                          onClick={() => cyclePermission('agent', agent.slug)}
                        >
                          {getPermissionBadge(perm)}
                        </Button>
                      ) : (
                        getPermissionBadge(perm)
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {activeTab === 'instances' && (
          <div className={styles.list}>
            {filteredInstances.length === 0 ? (
              <div className={styles.empty}>Нет коннекторов</div>
            ) : (
              filteredInstances.map((instance: ToolInstance) => {
                const perm = getInstancePermission(instance.slug);
                const isLocal = instance.placement === 'local';
                return (
                  <div key={instance.slug} className={styles.item}>
                    <div className={styles.itemInfo}>
                      <span className={styles.itemName}>
                        {instance.name}
                        {isLocal && (
                          <Badge tone="info" className={styles.localBadge}>
                            local
                          </Badge>
                        )}
                      </span>
                      <span className={styles.itemSlug}>{instance.slug}</span>
                    </div>
                    <div className={styles.itemAction}>
                      {editable ? (
                        <Button
                          variant="ghost"
                          size="small"
                          onClick={() => cyclePermission('instance', instance.slug)}
                        >
                          {getPermissionBadge(perm)}
                        </Button>
                      ) : (
                        getPermissionBadge(perm)
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <Badge tone="success">Разрешён</Badge> — доступ открыт
        </span>
        <span className={styles.legendItem}>
          <Badge tone="danger">Запрещён</Badge> — доступ закрыт
        </span>
        {scope !== 'default' && (
          <span className={styles.legendItem}>
            <Badge tone="neutral">Наследуется</Badge> — берётся из {scope === 'user' ? 'тенанта/default' : 'default'}
          </span>
        )}
      </div>
    </div>
  );
}

export default RbacRulesEditor;

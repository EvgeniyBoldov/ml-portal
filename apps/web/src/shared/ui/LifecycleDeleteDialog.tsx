import React, { useEffect, useMemo, useState } from 'react';
import ConfirmDialog from './ConfirmDialog';
import styles from './LifecycleDeleteDialog.module.css';
import {
  lifecycleApi,
  type DependencyEntity,
  type DependencyEntry,
  type LifecycleKind,
  type LifecycleReportResponse,
} from '@/shared/api/lifecycle';
import { ApiError } from '@/shared/api/errors';

type Props = {
  open: boolean;
  kind: LifecycleKind;
  entityId: string;
  entityLabel: string;
  isPlatformDefault?: boolean;
  onCancel: () => void;
  onSuccess: (report: LifecycleReportResponse) => void;
};

const GROUP_ORDER: Array<DependencyEntry['will_be']> = [
  'cascade_deleted',
  'migrated',
  'set_null',
  'already_deprecated',
  'blocker',
];

const GROUP_TITLE: Record<string, string> = {
  cascade_deleted: 'Будет удалено',
  migrated: 'Будет перенесено',
  set_null: 'Будет отвязано',
  already_deprecated: 'Уже помечено',
  blocker: 'Блокирует удаление',
};

const RESOURCE_TITLE: Record<string, string> = {
  users: 'Пользователи',
  tenants: 'Тенанты',
  collections: 'Коллекции',
  chats: 'Чаты',
  sandbox_sessions: 'Sandbox-сессии',
  rbac_rules: 'RBAC-правила',
  tenant_bindings: 'Привязки к тенантам',
  admin_guard: 'Ограничения',
};

function resourceLabel(type: string): string {
  return RESOURCE_TITLE[type] ?? type.replace(/_/g, ' ');
}

function groupAckLabel(groupType: string): string {
  if (groupType === 'cascade_deleted') return 'Подтверждаю каскадное удаление';
  if (groupType === 'migrated') return 'Подтверждаю перенос зависимостей';
  if (groupType === 'set_null') return 'Подтверждаю отвязку зависимостей';
  if (groupType === 'already_deprecated') return 'Подтверждаю текущий статус';
  return 'Подтверждаю';
}

type TreeNode = {
  id: string;
  title: string;
  count?: number;
  entities?: DependencyEntity[];
  children?: TreeNode[];
};

function AccordionTree({ nodes, level = 0 }: { nodes: TreeNode[]; level?: number }) {
  if (!nodes.length) return null;
  return (
    <>
      {nodes.map((node) => {
        const hasChildren = Boolean((node.children && node.children.length) || (node.entities && node.entities.length));
        if (!hasChildren) return null;
        return (
          <details key={node.id} className={level === 0 ? styles.accordion : styles.nestedAccordion}>
            <summary className={level === 0 ? styles.accordionSummary : styles.nestedAccordionSummary}>
              <span>{node.title}</span>
              <span>{node.count ?? (node.entities?.length || node.children?.length || 0)}</span>
            </summary>
            <div className={styles.entityList}>
              {node.entities?.map((entity) => (
                <a
                  key={entity.uuid}
                  className={styles.entityLink}
                  href={entity.url || '#'}
                  onClick={(e) => {
                    if (!entity.url) e.preventDefault();
                  }}
                  title={entity.uuid}
                >
                  {entity.name}
                </a>
              ))}
              {node.children && <AccordionTree nodes={node.children} level={level + 1} />}
            </div>
          </details>
        );
      })}
    </>
  );
}

function buildGroupTree(entries: DependencyEntry[]): TreeNode[] {
  const byResource = new Map<string, { count: number; entities: DependencyEntity[] }>();
  for (const entry of entries) {
    // Skip technical join tables
    if (entry.resource_type === 'tenant_bindings') continue;
    const curr = byResource.get(entry.resource_type) ?? { count: 0, entities: [] };
    curr.count += entry.count || 0;
    curr.entities.push(...(entry.entities ?? []));
    byResource.set(entry.resource_type, curr);
  }
  return Array.from(byResource.entries())
    .filter(([, data]) => data.count > 0)
    .map(([resourceType, data]) => ({
      id: `resource-${resourceType}`,
      title: resourceLabel(resourceType),
      count: data.count,
      entities: data.entities,
    }));
}

export default function LifecycleDeleteDialog({
  open,
  kind,
  entityId,
  entityLabel,
  isPlatformDefault = false,
  onCancel,
  onSuccess,
}: Props) {
  const [deleteNow, setDeleteNow] = useState(false);
  const [retentionDays, setRetentionDays] = useState<number>(14);
  const [deps, setDeps] = useState<DependencyEntry[]>([]);
  const [deleteDependents, setDeleteDependents] = useState(false);
  const [loadingDeps, setLoadingDeps] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [ack, setAck] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!open) return;
    setError('');
    setAck({});
    setDeleteNow(false);
    setDeleteDependents(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingDeps(true);
    lifecycleApi
      .getDependencies(kind, entityId, { cascade: deleteDependents, fullEntities: true })
      .then((res) => {
        if (!cancelled) setDeps(res.dependencies || []);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Не удалось загрузить зависимости');
      })
      .finally(() => {
        if (!cancelled) setLoadingDeps(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, kind, entityId, deleteDependents]);

  const renderGroups = useMemo(() => {
    // Filter out technical join tables that shouldn't be shown in UI
    const visibleDeps = deps.filter((d) => d.resource_type !== 'tenant_bindings');
    const byType = new Map<DependencyEntry['will_be'], DependencyEntry[]>();
    visibleDeps.forEach((item) => {
      // Skip technical join tables from processing
      if (item.resource_type === 'tenant_bindings') return;
      const isDirect = !item.details?.cascade_parent;
      const targetType = deleteDependents && isDirect ? 'cascade_deleted' : item.will_be;
      const arr = byType.get(targetType) ?? [];
      arr.push(item);
      byType.set(targetType, arr);
    });
    return GROUP_ORDER
      .map((groupType) => {
        const entries = byType.get(groupType) ?? [];
        // Filter out any remaining tenant_bindings just in case
        const filteredEntries = entries.filter((e) => e.resource_type !== 'tenant_bindings');
        const total = filteredEntries.reduce((acc, i) => acc + Number(i.count || 0), 0);
        return { groupType, entries: filteredEntries, total };
      })
      .filter((g) => g.entries.length > 0 && g.total > 0);
  }, [deps, deleteDependents]);

  const requiresAckKeys = useMemo(() => {
    return renderGroups
      .filter((g) => g.groupType !== 'blocker')
      .map((g) => g.groupType);
  }, [renderGroups]);

  const hasBlockers = useMemo(
    () => renderGroups.some((g) => g.groupType === 'blocker' && g.total > 0),
    [renderGroups],
  );

  const hasAllAcks = useMemo(() => requiresAckKeys.every((k) => ack[k] === true), [requiresAckKeys, ack]);

  const confirmLabel = deleteNow ? 'Удалить сейчас' : 'Пометить на удаление';
  const isDeleteDisabled = isPlatformDefault || saving || (deleteNow && (hasBlockers || !hasAllAcks));
  const dialogSize: 'md' | 'half' | 'lg' | 'xl' = 'lg';

  const handleConfirm = async () => {
    setSaving(true);
    setError('');
    try {
      const report = await lifecycleApi.deleteEntity(kind, entityId, {
        mode: deleteNow ? 'hard' : 'soft',
        force: deleteNow,
        cascade: deleteDependents,
        retention_days: !deleteNow ? retentionDays : undefined,
      });
      onSuccess(report);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError(typeof e.details === 'string' ? e.details : 'Удаление заблокировано зависимостями');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось выполнить удаление');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      title={`Удаление: ${entityLabel}`}
      confirmLabel={confirmLabel}
      cancelLabel="Отмена"
      variant="danger"
      size={dialogSize}
      confirmDisabled={isDeleteDisabled}
      confirmLoading={saving}
      onConfirm={handleConfirm}
      onCancel={onCancel}
      message="Выберите режим удаления и проверьте последствия."
    >
      <div className={styles.stack}>
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Режим удаления</div>
          <label className={styles.modeCheckbox}>
            <input
              type="checkbox"
              checked={deleteNow}
              onChange={(e) => setDeleteNow(e.target.checked)}
            />
            <span>Удалить сейчас</span>
          </label>
          {!deleteNow && (
            <label className={`${styles.fieldRow} ${styles.fieldRowInline}`}>
              <span className={styles.label}>Срок хранения (дней)</span>
              <input
                className={styles.input}
                type="number"
                min={0}
                max={3650}
                value={retentionDays}
                onChange={(e) => setRetentionDays(Number(e.target.value || 14))}
              />
              <span className={styles.hint}>Через сколько дней GC удалит запись окончательно</span>
            </label>
          )}
          <label className={styles.modeCheckbox}>
            <input
              type="checkbox"
              checked={deleteDependents}
              onChange={(e) => setDeleteDependents(e.target.checked)}
            />
            <span>Удалить зависимые</span>
          </label>
        </div>

        {isPlatformDefault && (
          <div className={styles.warningBox}>Нельзя удалить платформенный тенант по умолчанию</div>
        )}

        <div className={`${styles.section} ${styles.depsSection}`}>
          <div className={styles.hardHeaderRow}>
            <div className={styles.sectionTitle}>Последствия удаления сейчас</div>
          </div>
          {loadingDeps && <div className={styles.depMeta}>Загрузка зависимостей...</div>}
          {!loadingDeps && renderGroups.length === 0 && <div className={styles.depMeta}>Зависимости не найдены</div>}
          {!loadingDeps && renderGroups.length > 0 && (
            <div className={styles.groupsRow}>
              {renderGroups.map(({ groupType, entries, total }) => {
                  const tree = buildGroupTree(entries);

                  return (
                    <div key={groupType} className={styles.groupWrap}>
                      <div className={`${styles.groupCard} ${styles[`group_${groupType}`]} ${groupType === 'blocker' ? styles.groupBlocker : ''}`}>
                        <div className={styles.groupHeader}>
                          <span className={styles.groupTitle}>{GROUP_TITLE[groupType] ?? groupType}</span>
                          <strong className={styles.groupTotal}>{total}</strong>
                        </div>
                        <div className={styles.groupBody}>
                          <AccordionTree nodes={tree} />
                        </div>
                      </div>
                      <label className={styles.groupAck}>
                        <input
                          type="checkbox"
                          checked={groupType === 'blocker' ? true : ack[groupType] === true}
                          onChange={(e) => {
                            if (groupType === 'blocker') return;
                            setAck((prev) => ({ ...prev, [groupType]: e.target.checked }));
                          }}
                          disabled={groupType === 'blocker'}
                        />
                        <span>{groupType === 'blocker' ? 'Требует устранения блокера' : groupAckLabel(groupType)}</span>
                      </label>
                    </div>
                  );
              })}
            </div>
          )}
        </div>

        {error && <div className={styles.error}>{error}</div>}
      </div>
    </ConfirmDialog>
  );
}

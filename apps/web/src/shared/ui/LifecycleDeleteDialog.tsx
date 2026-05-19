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

export default function LifecycleDeleteDialog({
  open,
  kind,
  entityId,
  entityLabel,
  isPlatformDefault = false,
  onCancel,
  onSuccess,
}: Props) {
  const [mode, setMode] = useState<'soft' | 'hard'>('soft');
  const [reason, setReason] = useState('');
  const [retentionDays, setRetentionDays] = useState<number>(14);
  const [deps, setDeps] = useState<DependencyEntry[]>([]);
  const [cascadeMode, setCascadeMode] = useState(false);
  const [loadingDeps, setLoadingDeps] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [ack, setAck] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!open) return;
    setError('');
    setAck({});
  }, [open]);

  useEffect(() => {
    if (!open || mode !== 'hard') return;
    let cancelled = false;
    setLoadingDeps(true);
    lifecycleApi
      .getDependencies(kind, entityId)
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
  }, [open, mode, kind, entityId]);

  const groupedDeps = useMemo(() => {
    const byType = new Map<DependencyEntry['will_be'], DependencyEntry[]>();
    for (const item of deps) {
      const arr = byType.get(item.will_be) ?? [];
      arr.push(item);
      byType.set(item.will_be, arr);
    }
    return byType;
  }, [deps]);

  const visibleGroups = useMemo(() => {
    return GROUP_ORDER
      .map((groupType) => {
        const entries = groupedDeps.get(groupType) ?? [];
        const total = entries.reduce((acc, i) => acc + Number(i.count || 0), 0);
        return { groupType, entries, total };
      })
      .filter((g) => g.entries.length > 0 && g.total > 0);
  }, [groupedDeps]);

  const renderGroups = useMemo(() => {
    if (!cascadeMode) return visibleGroups;
    const allEntries = visibleGroups.flatMap((g) => g.entries);
    const total = visibleGroups.reduce((acc, g) => acc + g.total, 0);
    if (!allEntries.length || total <= 0) return [];
    return [{ groupType: 'cascade_deleted' as const, entries: allEntries, total }];
  }, [cascadeMode, visibleGroups]);

  const requiresAckKeys = useMemo(() => {
    return renderGroups
      .filter((g) => g.groupType !== 'blocker')
      .map((g) => g.groupType);
  }, [renderGroups]);

  const hasBlockers = useMemo(
    () => visibleGroups.some((g) => g.groupType === 'blocker' && g.total > 0),
    [visibleGroups],
  );

  const hasAllAcks = useMemo(() => requiresAckKeys.every((k) => ack[k] === true), [requiresAckKeys, ack]);

  const confirmLabel = mode === 'soft' ? 'Пометить на удаление' : 'Удалить сейчас';
  const isDeleteDisabled = isPlatformDefault || saving || (mode === 'hard' && (hasBlockers || !hasAllAcks));
  const dialogSize: 'md' | 'half' | 'lg' | 'xl' = mode === 'hard' ? 'lg' : 'md';

  const handleConfirm = async () => {
    setSaving(true);
    setError('');
    try {
      const report = await lifecycleApi.deleteEntity(kind, entityId, {
        mode,
        force: mode === 'hard',
        reason: mode === 'soft' ? reason : undefined,
        retention_days: mode === 'soft' ? retentionDays : undefined,
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
          <div className={styles.modeRow}>
            <button
              className={`${styles.modeBtn} ${mode === 'soft' ? styles.modeBtnActive : ''}`}
              type="button"
              onClick={() => setMode('soft')}
            >
              Пометить на удаление
            </button>
            <button
              className={`${styles.modeBtn} ${mode === 'hard' ? styles.modeBtnActive : ''}`}
              type="button"
              onClick={() => setMode('hard')}
            >
              Удалить сейчас
            </button>
          </div>
        </div>

        {isPlatformDefault && (
          <div className={styles.warningBox}>Нельзя удалить платформенный тенант по умолчанию</div>
        )}

        {mode === 'soft' ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Параметры пометки на удаление</div>
            <label className={styles.fieldRow}>
              <span className={styles.label}>Причина</span>
              <textarea
                className={styles.textarea}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Коротко: зачем помечаем на удаление"
              />
            </label>
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
          </div>
        ) : (
          <div className={`${styles.section} ${styles.depsSection}`}>
            <div className={styles.hardHeaderRow}>
              <div className={styles.sectionTitle}>Последствия удаления сейчас</div>
              <label className={styles.cascadeToggle}>
                <input
                  type="checkbox"
                  checked={cascadeMode}
                  onChange={(e) => setCascadeMode(e.target.checked)}
                />
                <span>Каскадное удаление</span>
              </label>
            </div>
            {loadingDeps && <div className={styles.depMeta}>Загрузка зависимостей...</div>}
            {!loadingDeps && visibleGroups.length === 0 && <div className={styles.depMeta}>Зависимости не найдены</div>}
            {!loadingDeps && visibleGroups.length > 0 && (
              <div className={styles.groupsRow}>
                {renderGroups.map(({ groupType, entries, total }) => {
                  const byResource = new Map<string, DependencyEntity[]>();
                  entries.forEach((entry) => {
                    const curr = byResource.get(entry.resource_type) ?? [];
                    curr.push(...(entry.entities ?? []));
                    byResource.set(entry.resource_type, curr);
                  });

                  return (
                    <div key={groupType} className={styles.groupWrap}>
                      <div className={`${styles.groupCard} ${styles[`group_${groupType}`]} ${groupType === 'blocker' ? styles.groupBlocker : ''}`}>
                        <div className={styles.groupHeader}>
                          <span className={styles.groupTitle}>{GROUP_TITLE[groupType] ?? groupType}</span>
                          <strong className={styles.groupTotal}>{total}</strong>
                        </div>
                        <div className={styles.groupBody}>
                          {Array.from(byResource.entries()).map(([resourceType, entities]) => (
                            <details key={`${groupType}-${resourceType}`} className={styles.accordion} open>
                              <summary className={styles.accordionSummary}>
                                <span>{resourceLabel(resourceType)}</span>
                                <span>{entities.length}</span>
                              </summary>
                              <div className={styles.entityList}>
                                {entities.map((entity) => (
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
                              </div>
                            </details>
                          ))}
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
        )}

        {error && <div className={styles.error}>{error}</div>}
      </div>
    </ConfirmDialog>
  );
}

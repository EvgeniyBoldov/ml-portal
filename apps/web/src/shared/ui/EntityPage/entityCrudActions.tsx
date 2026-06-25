import type { ReactNode } from 'react';
import Button from '../Button';
import type { EntityPageMode } from './EntityPageV2';
import { ADMIN_ACTION_LABELS } from '@/shared/constants/adminLabels';

type LifecycleStatus = 'active' | 'deprecated' | string;
type CrudTone = 'default' | 'success';
type ExtraPosition = 'beforeCrud' | 'afterCrud';

interface CrudActionLabels {
  edit?: string;
  save?: string;
  cancel?: string;
  create?: string;
  delete?: string;
  restore?: string;
}

interface EntityCrudActionsParams {
  mode: EntityPageMode;
  saving?: boolean;
  lifecycleStatus?: LifecycleStatus;
  onEdit?: () => void;
  onSave?: () => void;
  onCancel?: () => void;
  onDelete?: () => void;
  onRestore?: () => void;
  restorePending?: boolean;
  showDeleteInView?: boolean;
  tone?: CrudTone;
  labels?: CrudActionLabels;
}

export function buildEntityCrudActions({
  mode,
  saving = false,
  lifecycleStatus,
  onEdit,
  onSave,
  onCancel,
  onDelete,
  onRestore,
  restorePending = false,
  showDeleteInView = true,
  tone = 'default',
  labels,
}: EntityCrudActionsParams): ReactNode[] {
  const primaryVariant = tone === 'success' ? 'success' : 'primary';
  const editLabel = labels?.edit ?? ADMIN_ACTION_LABELS.edit;
  const saveLabel = labels?.save ?? ADMIN_ACTION_LABELS.save;
  const cancelLabel = labels?.cancel ?? ADMIN_ACTION_LABELS.cancel;
  const createLabel = labels?.create ?? ADMIN_ACTION_LABELS.create;
  const deleteLabel = labels?.delete ?? ADMIN_ACTION_LABELS.delete;
  const restoreLabel = labels?.restore ?? ADMIN_ACTION_LABELS.restore;

  if (mode === 'view') {
    const actions: ReactNode[] = [];
    if (lifecycleStatus === 'deprecated' && onRestore) {
      actions.push(
        <Button key="restore" variant="outline" onClick={onRestore} disabled={restorePending}>
          {restoreLabel}
        </Button>,
      );
    }
    if (onEdit && lifecycleStatus !== 'deprecated') {
      actions.push(
        <Button key="edit" variant={primaryVariant} onClick={onEdit}>
          {editLabel}
        </Button>,
      );
    }
    if (showDeleteInView && onDelete) {
      actions.push(
        <Button key="delete" variant="danger" onClick={onDelete}>
          {deleteLabel}
        </Button>,
      );
    }
    return actions;
  }

  if (mode === 'edit') {
    return [
      <Button key="save" variant={primaryVariant} onClick={onSave} disabled={saving}>
        {saving ? 'Сохранение...' : saveLabel}
      </Button>,
      <Button key="cancel" variant="outline" onClick={onCancel}>
        {cancelLabel}
      </Button>,
    ];
  }

  if (mode === 'create') {
    return [
      <Button key="cancel" variant="outline" onClick={onCancel} disabled={saving}>
        {cancelLabel}
      </Button>,
      <Button key="create" variant={primaryVariant} onClick={onSave} disabled={saving}>
        {saving ? 'Создание...' : createLabel}
      </Button>,
    ];
  }

  return [];
}

interface ComposeEntityActionsParams {
  crud: ReactNode[];
  extra?: ReactNode[];
  extraPosition?: ExtraPosition;
}

export function composeEntityActions({
  crud,
  extra = [],
  extraPosition = 'afterCrud',
}: ComposeEntityActionsParams): ReactNode[] {
  return extraPosition === 'beforeCrud'
    ? [...extra, ...crud]
    : [...crud, ...extra];
}

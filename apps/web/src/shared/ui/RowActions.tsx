/**
 * RowActions - Unified row actions component for admin tables
 * Provides consistent view/edit/delete actions with optional custom actions
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ActionsButton, type ActionItem } from './ActionsButton';

export interface RowActionsProps {
  /** Base path for view/edit routes (e.g., '/admin/policies') */
  basePath: string;
  /** Row ID for building routes */
  id: string;
  /** Show view action */
  viewable?: boolean;
  /** Show edit action */
  editable?: boolean;
  /** Show delete action */
  deletable?: boolean;
  /** Delete handler */
  onDelete?: () => void;
  /** Is delete in progress */
  deleteLoading?: boolean;
  /** Additional custom actions */
  customActions?: ActionItem[];
  /** Custom view handler (overrides navigation) */
  onView?: () => void;
  /** Custom edit handler (overrides navigation) */
  onEdit?: () => void;
}

export function RowActions({
  basePath,
  id,
  viewable = true,
  editable = true,
  deletable = true,
  onDelete,
  deleteLoading = false,
  customActions = [],
  onView,
  onEdit,
}: RowActionsProps) {
  const navigate = useNavigate();

  const actions: ActionItem[] = [];

  if (viewable) {
    actions.push({
      label: 'Просмотр',
      onClick: onView || (() => navigate(`${basePath}/${id}`)),
    });
  }

  if (editable) {
    actions.push({
      label: 'Редактировать',
      onClick: onEdit || (() => navigate(`${basePath}/${id}/edit`)),
    });
  }

  // Add custom actions between edit and delete
  actions.push(...customActions);

  if (deletable && onDelete) {
    actions.push({
      label: 'Удалить',
      onClick: onDelete,
      variant: 'danger',
      disabled: deleteLoading,
    });
  }

  if (actions.length === 0) return null;

  return <ActionsButton actions={actions} />;
}

export default RowActions;

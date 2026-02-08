/**
 * useVersionActions - Universal hook for version action buttons
 * 
 * Returns React nodes for EntityPage.actionButtons based on version status:
 * - draft → Редактировать + Активировать
 * - active → Деактивировать + Сделать основной (if not recommended)
 * - inactive/archived → Активировать
 * 
 * Supports extra actions via extraActions prop.
 * Always returns a ReactNode (empty fragment if no actions) to prevent
 * EntityPage from showing default buttons.
 */
import React from 'react';
import { Button } from '@/shared/ui';

export interface VersionActionCallbacks {
  onActivate?: () => void;
  onDeactivate?: () => void;
  onSetRecommended?: () => void;
  onEdit?: () => void;
}

export interface VersionActionLoadingState {
  activate?: boolean;
  deactivate?: boolean;
  setRecommended?: boolean;
}

export interface UseVersionActionsOptions {
  status: string | undefined;
  isRecommended: boolean;
  isCreate: boolean;
  callbacks: VersionActionCallbacks;
  loading?: VersionActionLoadingState;
  extraActions?: React.ReactNode[];
}

export function useVersionActions({
  status,
  isRecommended,
  isCreate,
  callbacks,
  loading = {},
  extraActions = [],
}: UseVersionActionsOptions): React.ReactNode {
  if (isCreate || !status) return null;

  const buttons: React.ReactNode[] = [];

  switch (status) {
    case 'draft':
      if (callbacks.onEdit) {
        buttons.push(
          <Button
            key="edit"
            variant="outline"
            onClick={callbacks.onEdit}
          >
            Редактировать
          </Button>
        );
      }
      if (callbacks.onActivate) {
        buttons.push(
          <Button
            key="activate"
            variant="primary"
            onClick={callbacks.onActivate}
            disabled={loading.activate}
            loading={loading.activate}
          >
            Активировать
          </Button>
        );
      }
      break;

    case 'active':
      if (!isRecommended && callbacks.onSetRecommended) {
        buttons.push(
          <Button
            key="setRecommended"
            variant="outline"
            onClick={callbacks.onSetRecommended}
            disabled={loading.setRecommended}
            loading={loading.setRecommended}
          >
            Сделать основной
          </Button>
        );
      }
      if (callbacks.onDeactivate) {
        buttons.push(
          <Button
            key="deactivate"
            variant="danger"
            onClick={callbacks.onDeactivate}
            disabled={loading.deactivate}
            loading={loading.deactivate}
          >
            Деактивировать
          </Button>
        );
      }
      break;

    case 'inactive':
    case 'archived':
      if (callbacks.onActivate) {
        buttons.push(
          <Button
            key="reactivate"
            variant="primary"
            onClick={callbacks.onActivate}
            disabled={loading.activate}
            loading={loading.activate}
          >
            Активировать
          </Button>
        );
      }
      break;
  }

  // Append extra actions
  buttons.push(...extraActions);

  // Always return a fragment (even empty) to override EntityPage defaults
  return <>{buttons}</>;
}

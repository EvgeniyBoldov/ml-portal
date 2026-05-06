import React from 'react';
import { Button } from '@/shared/ui';

export type UnifiedVersionStatus = 'draft' | 'published' | 'archived';

export interface VersionLifecycleCallbacks {
  onEdit?: () => void;
  onPublish?: () => void;
  onSetPrimary?: () => void;
  onArchive?: () => void;
  onClone?: () => void;
}

export interface VersionLifecycleLoadingState {
  publish?: boolean;
  primary?: boolean;
  archive?: boolean;
}

export interface UseVersionLifecycleActionsOptions {
  status: string | undefined;
  isCreate: boolean;
  isPrimary: boolean;
  callbacks: VersionLifecycleCallbacks;
  loading?: VersionLifecycleLoadingState;
}

export function normalizeVersionStatus(status: string | undefined): UnifiedVersionStatus | null {
  if (!status) return null;
  if (status === 'draft') return 'draft';
  if (status === 'published' || status === 'active') return 'published';
  if (status === 'archived') return 'archived';
  return null;
}

export function getVersionStatusPresentation(status: string | undefined): {
  label: string;
  tone: 'success' | 'warn' | 'neutral';
} {
  const normalized = normalizeVersionStatus(status);
  switch (normalized) {
    case 'published':
      return { label: 'Опубликована', tone: 'success' };
    case 'archived':
      return { label: 'В архиве', tone: 'neutral' };
    case 'draft':
    default:
      return { label: 'Черновик', tone: 'warn' };
  }
}

export function useVersionLifecycleActions({
  status,
  isCreate,
  isPrimary,
  callbacks,
  loading = {},
}: UseVersionLifecycleActionsOptions): React.ReactNode {
  const normalizedStatus = normalizeVersionStatus(status);
  if (isCreate || !normalizedStatus) return null;

  const buttons: React.ReactNode[] = [];

  if (normalizedStatus === 'draft') {
    if (callbacks.onEdit) {
      buttons.push(
        <Button
          key="edit"
          variant="outline"
          onClick={callbacks.onEdit}
        >
          Редактировать
        </Button>,
      );
    }
    if (callbacks.onPublish) {
      buttons.push(
        <Button
          key="publish"
          variant="primary"
          onClick={callbacks.onPublish}
          disabled={loading.publish}
          loading={loading.publish}
        >
          Опубликовать
        </Button>,
      );
    }
  }

  if (normalizedStatus === 'published') {
    if (!isPrimary && callbacks.onSetPrimary) {
      buttons.push(
        <Button
          key="primary"
          variant="primary"
          onClick={callbacks.onSetPrimary}
          disabled={loading.primary}
          loading={loading.primary}
        >
          Сделать основной
        </Button>,
      );
    }
    if (!isPrimary && callbacks.onArchive) {
      buttons.push(
        <Button
          key="archive"
          variant="warning"
          onClick={callbacks.onArchive}
          disabled={loading.archive}
          loading={loading.archive}
        >
          В архив
        </Button>,
      );
    }
  }

  if (callbacks.onClone) {
    buttons.push(
      <Button key="clone" variant="outline" onClick={callbacks.onClone}>
        Clone
      </Button>,
    );
  }

  return <>{buttons}</>;
}

export default useVersionLifecycleActions;

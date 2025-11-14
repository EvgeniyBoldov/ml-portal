/**
 * GlobalConfirmDialog - Renders confirm dialog from Zustand store
 */
import React from 'react';
import { useAppStore } from '../store/app.store';
import ConfirmDialog from '@shared/ui/ConfirmDialog';

export function GlobalConfirmDialog() {
  const confirmDialog = useAppStore(state => state.confirmDialog);
  const hideConfirmDialog = useAppStore(state => state.hideConfirmDialog);
  const confirmAndClose = useAppStore(state => state.confirmAndClose);

  return (
    <ConfirmDialog
      open={confirmDialog.open}
      title={confirmDialog.title}
      message={confirmDialog.message}
      confirmLabel={confirmDialog.confirmLabel}
      cancelLabel={confirmDialog.cancelLabel}
      variant={confirmDialog.variant}
      onConfirm={confirmAndClose}
      onCancel={hideConfirmDialog}
    />
  );
}

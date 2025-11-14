import React, { useState } from 'react';
import Popover from '@shared/ui/Popover';
import styles from './ActionsButton.module.css';

export interface ActionItem {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}

interface ActionsButtonProps {
  actions: ActionItem[];
  className?: string;
}

export function ActionsButton({ actions, className }: ActionsButtonProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleActionClick = (action: ActionItem) => {
    if (!action.disabled) {
      action.onClick();
      setIsOpen(false);
    }
  };

  return (
    <Popover
      open={isOpen}
      onOpenChange={setIsOpen}
      side="top"
      align="end"
      trigger={
        <button
          type="button"
          className={`${styles.menuButton} ${className || ''}`}
        >
          ⋯
        </button>
      }
      content={
        <div
          className={styles.popoverContent}
          onClick={e => e.stopPropagation()}
          onMouseDown={e => e.stopPropagation()}
        >
          {actions.map((action, index) => (
            <button
              key={index}
              type="button"
              onClick={e => {
                e.preventDefault();
                e.stopPropagation();
                handleActionClick(action);
              }}
              onMouseDown={e => {
                e.preventDefault();
                e.stopPropagation();
              }}
              disabled={action.disabled}
              className={`${styles.actionButton} ${action.danger ? styles.dangerButton : ''}`}
            >
              {action.label}
            </button>
          ))}
        </div>
      }
    />
  );
}

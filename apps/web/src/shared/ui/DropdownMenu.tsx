import React, { useRef, useEffect, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './DropdownMenu.module.css';

export interface DropdownMenuItem {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
  variant?: 'default' | 'danger';
  disabled?: boolean;
}

export interface DropdownMenuProps {
  items: DropdownMenuItem[];
  isOpen: boolean;
  onClose: () => void;
  anchorEl?: HTMLElement | null;
  anchorPosition?: { x: number; y: number };
}

/**
 * DropdownMenu - accessible action menu
 * - role="menu" with keyboard navigation (arrows, Esc, Enter)
 * - Returns focus to trigger on close
 * - Portal rendering for z-index safety
 */
export function DropdownMenu({
  items,
  isOpen,
  onClose,
  anchorEl,
  anchorPosition,
}: DropdownMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Store trigger element on mount
  useEffect(() => {
    if (isOpen && !triggerRef.current) {
      triggerRef.current = document.activeElement as HTMLElement;
    }
  }, [isOpen]);

  // Return focus to trigger on close
  useEffect(() => {
    if (!isOpen && triggerRef.current) {
      triggerRef.current.focus();
      triggerRef.current = null;
    }
  }, [isOpen]);

  // Focus first item when opened
  useEffect(() => {
    if (isOpen && menuRef.current) {
      setFocusedIndex(0);
      const firstItem = menuRef.current.querySelector<HTMLButtonElement>(
        '[role="menuitem"]:not([disabled])'
      );
      firstItem?.focus();
    }
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const enabledItems = items.filter(item => !item.disabled);
      const enabledCount = enabledItems.length;

      switch (e.key) {
        case 'Escape':
          e.preventDefault();
          onClose();
          break;

        case 'ArrowDown':
          e.preventDefault();
          setFocusedIndex(prev => {
            const next = (prev + 1) % enabledCount;
            const buttons = menuRef.current?.querySelectorAll<HTMLButtonElement>(
              '[role="menuitem"]:not([disabled])'
            );
            buttons?.[next]?.focus();
            return next;
          });
          break;

        case 'ArrowUp':
          e.preventDefault();
          setFocusedIndex(prev => {
            const next = (prev - 1 + enabledCount) % enabledCount;
            const buttons = menuRef.current?.querySelectorAll<HTMLButtonElement>(
              '[role="menuitem"]:not([disabled])'
            );
            buttons?.[next]?.focus();
            return next;
          });
          break;

        case 'Enter':
        case ' ':
          e.preventDefault();
          const buttons = menuRef.current?.querySelectorAll<HTMLButtonElement>(
            '[role="menuitem"]:not([disabled])'
          );
          buttons?.[focusedIndex]?.click();
          break;
      }
    },
    [items, focusedIndex, onClose]
  );

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Calculate position
  const getPosition = () => {
    if (anchorPosition) {
      return { top: anchorPosition.y, left: anchorPosition.x };
    }
    if (anchorEl) {
      const rect = anchorEl.getBoundingClientRect();
      return { top: rect.bottom + 4, left: rect.left };
    }
    return { top: 0, left: 0 };
  };

  const position = getPosition();

  const menu = (
    <div
      ref={menuRef}
      role="menu"
      className={styles.dropdownMenu}
      style={{ top: position.top, left: position.left }}
      onKeyDown={handleKeyDown}
    >
      {items.map((item, index) => (
        <button
          key={index}
          role="menuitem"
          type="button"
          disabled={item.disabled}
          className={`${styles.menuItem} ${
            item.variant === 'danger' ? styles.danger : ''
          }`}
          onClick={() => {
            if (!item.disabled) {
              item.onClick();
              onClose();
            }
          }}
          tabIndex={-1}
        >
          {item.icon && <span className={styles.icon}>{item.icon}</span>}
          <span className={styles.label}>{item.label}</span>
        </button>
      ))}
    </div>
  );

  return createPortal(menu, document.body);
}

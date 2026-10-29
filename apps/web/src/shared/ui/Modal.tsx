import React, { useId, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import styles from './Modal.module.css';
import Button from './Button';

const openModals: symbol[] = [];

type Size = 'md' | 'half' | 'lg' | 'xl' | 'fit';

type Props = {
  open: boolean;
  title?: string;
  onClose: () => void;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  size?: Size;
  className?: string;
  bodyClassName?: string;
};

export default function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  size = 'md',
  className,
  bodyClassName,
}: Props) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const modalId = useRef(Symbol('modal'));
  const wasOpen = useRef(false);
  const openerRef = useRef<HTMLElement | null>(null);
  if (open && !wasOpen.current) {
    openerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
  }
  wasOpen.current = open;
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useLayoutEffect(() => {
    if (!open || !dialogRef.current) return;
    const dialog = dialogRef.current;
    const id = modalId.current;
    const previousFocus = openerRef.current;
    openModals.push(id);
    const ownedPopups = new Set<HTMLElement>();
    const isInScope = (node: globalThis.Node | null): boolean =>
      !!node &&
      (dialog.contains(node) ||
        [...ownedPopups].some(
          popup => popup.isConnected && popup.contains(node)
        ));
    const isTopModal = () => openModals[openModals.length - 1] === id;
    const focusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button, input:not([type="hidden"]), textarea, select, [tabindex]'
        )
      ).filter(
        node =>
          node.tabIndex >= 0 &&
          !node.matches(':disabled') &&
          !node.closest('[hidden], [inert]') &&
          window.getComputedStyle(node).display !== 'none' &&
          window.getComputedStyle(node).visibility !== 'hidden'
      );
    const focusInside = () => {
      const initial =
        dialog.querySelector<HTMLElement>('[autofocus]') ||
        focusable().find(node => node.matches('input, textarea, select')) ||
        focusable()[0];
      (initial || dialog).focus();
    };
    if (!dialog.contains(document.activeElement)) focusInside();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isTopModal() || event.defaultPrevented) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeRef.current();
      } else if (event.key === 'Tab') {
        const nodes = focusable();
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (
          !nodes.length ||
          !dialog.contains(document.activeElement) ||
          (event.shiftKey
            ? document.activeElement === first
            : document.activeElement === last)
        ) {
          event.preventDefault();
          event.stopImmediatePropagation();
          (event.shiftKey ? last || dialog : first || dialog).focus();
        }
      }
    };
    const handleFocus = (event: globalThis.FocusEvent) => {
      if (!isTopModal()) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (isInScope(target)) return;
      const popup = target?.closest<HTMLElement>(
        '[role="menu"], [role="listbox"]'
      );
      if (popup && isInScope(event.relatedTarget as globalThis.Node | null)) {
        ownedPopups.add(popup);
        return;
      }
      focusInside();
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('focusin', handleFocus);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('focusin', handleFocus);
      const index = openModals.indexOf(id);
      if (index !== -1) openModals.splice(index, 1);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open]);

  if (!open) return null;

  const bodyClasses = [styles.body, bodyClassName].filter(Boolean).join(' ');

  return createPortal(
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={[
          styles.modal,
          size === 'half' ? styles.half : '',
          size === 'lg' ? styles.large : '',
          size === 'xl' ? styles.xl : '',
          size === 'fit' ? styles.fit : '',
          className || '',
        ].join(' ')}
        onClick={e => e.stopPropagation()}
      >
        <div className={styles.head}>
          {title && (
            <div id={titleId} className={styles.title}>
              {title}
            </div>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={onClose}
            aria-label="Закрыть"
          >
            ✕
          </Button>
        </div>
        <div className={bodyClasses}>{children}</div>
        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

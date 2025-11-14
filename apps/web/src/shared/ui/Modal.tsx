import React from 'react';
import styles from './Modal.module.css';
import Button from './Button';

type Size = 'md' | 'half' | 'lg' | 'xl';

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
  if (!open) return null;

  const bodyClasses = [styles.body, bodyClassName].filter(Boolean).join(' ');

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      <div
        className={[
          styles.modal,
          size === 'half' ? styles.half : '',
          size === 'lg' ? styles.large : '',
          size === 'xl' ? styles.xl : '',
          className || '',
        ].join(' ')}
        onClick={e => e.stopPropagation()}
      >
        <div className={styles.head}>
          {title && (
            <div id="modal-title" className={styles.title}>
              {title}
            </div>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </Button>
        </div>
        <div className={bodyClasses}>{children}</div>
        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </div>
  );
}

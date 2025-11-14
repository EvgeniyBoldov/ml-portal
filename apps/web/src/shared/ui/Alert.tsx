import React from 'react';
import styles from './Alert.module.css';

export type AlertVariant =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger';

interface AlertProps {
  variant?: AlertVariant;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

const variantIcon: Record<AlertVariant, React.ReactNode> = {
  neutral: '💡',
  info: 'ℹ️',
  success: '✅',
  warning: '⚠️',
  danger: '🚨',
};

export default function Alert({
  variant = 'info',
  title,
  description,
  children,
  icon,
  className = '',
}: AlertProps) {
  const variantClass = styles[variant] ?? styles.neutral;
  const resolvedIcon = icon ?? variantIcon[variant];
  const body = description ?? children;
  const alertClassName = [styles.alert, variantClass, className]
    .filter(Boolean)
    .join(' ');
  const ariaLive =
    variant === 'danger' || variant === 'warning' ? 'assertive' : 'polite';

  return (
    <div className={alertClassName} role="alert" aria-live={ariaLive}>
      {resolvedIcon && (
        <span className={styles.icon} aria-hidden="true">
          {resolvedIcon}
        </span>
      )}
      <div className={styles.body}>
        {title && <p className={styles.title}>{title}</p>}
        {body && (
          <div className={styles.description}>
            {typeof body === 'string' ? <p>{body}</p> : body}
          </div>
        )}
      </div>
    </div>
  );
}

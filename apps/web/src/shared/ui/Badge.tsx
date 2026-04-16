import React from 'react';
import styles from './Badge.module.css';

type Props = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
  size?: 'small' | 'medium' | 'large' | 'sm' | 'md' | 'lg';
  children: React.ReactNode;
  className?: string;
};

export default function Badge({
  tone = 'neutral',
  size = 'medium',
  className = '',
  children,
  ...rest
}: Props) {
  const normalizedSize =
    size === 'sm' ? 'small' : size === 'md' ? 'medium' : size === 'lg' ? 'large' : size;
  return (
    <span
      {...rest}
      className={[styles.badge, styles[normalizedSize], styles[tone], className].join(' ')}
    >
      {children}
    </span>
  );
}

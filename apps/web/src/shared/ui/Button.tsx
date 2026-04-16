import React from 'react';
import styles from './Button.module.css';

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger' | 'outline' | 'warning' | 'success';
  size?: 'md' | 'sm' | 'small' | 'lg';
  loading?: boolean;
};

export default function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  loading = false,
  ...rest
}: Props) {
  const sizeClass = size === 'small' ? 'sm' : size;
  const cls = [styles.btn, styles[variant], styles[sizeClass], className].join(
    ' '
  );
  return <button {...rest} className={cls} disabled={rest.disabled || loading} aria-busy={loading || undefined} />;
}

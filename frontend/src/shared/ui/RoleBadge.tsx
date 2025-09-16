import React from 'react';
import styles from './RoleBadge.module.css';

export interface RoleBadgeProps {
  role: 'admin' | 'editor' | 'reader';
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

export function RoleBadge({ role, size = 'medium', className = '' }: RoleBadgeProps) {
  const getRoleLabel = (role: string) => {
    switch (role) {
      case 'admin':
        return 'Admin';
      case 'editor':
        return 'Editor';
      case 'reader':
        return 'Reader';
      default:
        return role;
    }
  };

  return (
    <span className={`${styles.badge} ${styles[role]} ${styles[size]} ${className}`}>
      {getRoleLabel(role)}
    </span>
  );
}

export interface StatusBadgeProps {
  active: boolean;
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

export function StatusBadge({ active, size = 'medium', className = '' }: StatusBadgeProps) {
  return (
    <span className={`${styles.badge} ${active ? styles.active : styles.inactive} ${styles[size]} ${className}`}>
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}

export default RoleBadge;

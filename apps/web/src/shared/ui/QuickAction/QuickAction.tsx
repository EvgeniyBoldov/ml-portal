/**
 * QuickAction - Quick action button for Dashboard
 * 
 * Replaces duplicated quick action markup
 */
import React from 'react';
import { Link } from 'react-router-dom';
import styles from './QuickAction.module.css';

export interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  href: string;
  className?: string;
}

export function QuickAction({ icon, label, href, className = '' }: QuickActionProps) {
  return (
    <Link to={href} className={`${styles.quickAction} ${className}`}>
      <span className={styles.quickActionIcon}>{icon}</span>
      <span className={styles.quickActionLabel}>{label}</span>
    </Link>
  );
}

export interface QuickActionGridProps {
  children: React.ReactNode;
  className?: string;
}

export function QuickActionGrid({ children, className = '' }: QuickActionGridProps) {
  return (
    <div className={`${styles.quickActionGrid} ${className}`}>
      {children}
    </div>
  );
}

export default QuickAction;

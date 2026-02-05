/**
 * EntityCard - Reusable card component for Dashboard and list pages
 * 
 * Replaces duplicated card markup across admin pages
 */
import React from 'react';
import styles from './EntityCard.module.css';

export interface EntityCardProps {
  title: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function EntityCard({
  title,
  icon,
  actions,
  children,
  className = '',
}: EntityCardProps) {
  return (
    <section className={`${styles.card} ${className}`}>
      <div className={styles.cardHeader}>
        <div className={styles.cardTitle}>
          {icon && <span className={styles.cardIcon}>{icon}</span>}
          <h2>{title}</h2>
        </div>
        {actions && <div className={styles.cardActions}>{actions}</div>}
      </div>
      <div className={styles.cardContent}>
        {children}
      </div>
    </section>
  );
}

export interface EntityCardItemProps {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  badges?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

export function EntityCardItem({
  title,
  subtitle,
  badge,
  badges,
  onClick,
  className = '',
}: EntityCardItemProps) {
  const handleClick = onClick ? { onClick, role: 'button', tabIndex: 0 } : {};
  
  return (
    <div 
      className={`${styles.listItem} ${onClick ? styles.clickable : ''} ${className}`}
      {...handleClick}
    >
      <div className={styles.listItemMain}>
        <span className={styles.listItemTitle}>{title}</span>
        {subtitle && <span className={styles.listItemSub}>{subtitle}</span>}
      </div>
      {badge && <div className={styles.listItemBadge}>{badge}</div>}
      {badges && <div className={styles.listItemBadges}>{badges}</div>}
    </div>
  );
}

EntityCard.Item = EntityCardItem;

export default EntityCard;

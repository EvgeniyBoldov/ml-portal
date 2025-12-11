import React from 'react';
import { Icon } from '@shared/ui/Icon';
import styles from './StatCard.module.css';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  trend?: {
    value: number;
    label: string;
  };
  color?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
}

export function StatCard({ title, value, icon, trend, color = 'primary' }: StatCardProps) {
  return (
    <div className={`${styles.card} ${styles[color]}`}>
      <div className={styles.iconWrap}>
        <Icon name={icon} size={24} />
      </div>
      <div className={styles.content}>
        <div className={styles.value}>{value}</div>
        <div className={styles.title}>{title}</div>
        {trend && (
          <div className={`${styles.trend} ${trend.value >= 0 ? styles.trendUp : styles.trendDown}`}>
            <Icon name={trend.value >= 0 ? 'chevron-up' : 'chevron-down'} size={14} />
            <span>{Math.abs(trend.value)}% {trend.label}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * PageHeader - Unified header component for admin pages
 * 
 * Structure:
 * [Breadcrumbs?]
 * [BackButton?] [Title + Subtitle] [Spacer] [Actions]
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../Button';
import Input from '../Input';
import { Breadcrumbs, type BreadcrumbItem } from '../Breadcrumbs';
import styles from './PageHeader.module.css';

export interface PageHeaderAction {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'outline' | 'ghost' | 'danger';
  disabled?: boolean;
}

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  backTo?: string;
  
  // Breadcrumbs navigation
  breadcrumbs?: BreadcrumbItem[];
  
  // Search
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  
  // Actions (buttons)
  actions?: PageHeaderAction[];
  
  // Custom controls (for filters, etc)
  customControls?: React.ReactNode;
}

export function PageHeader({
  title,
  subtitle,
  backTo,
  breadcrumbs,
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Поиск...',
  actions = [],
  customControls,
}: PageHeaderProps) {
  const navigate = useNavigate();

  return (
    <div className={styles.header}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs items={breadcrumbs} className={styles.breadcrumbs} />
      )}
      <div className={styles.headerRow}>
        <div className={styles.left}>
          {backTo && (
            <button
              className={styles.backButton}
              onClick={() => navigate(backTo)}
              aria-label="Назад"
            >
              ←
            </button>
          )}
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>{title}</h1>
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
        </div>

        <div className={styles.controls}>
          {customControls}
          
          {onSearchChange && (
            <Input
              placeholder={searchPlaceholder}
              value={searchValue || ''}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => onSearchChange(e.target.value)}
              className={styles.search}
            />
          )}

          {actions.map((action, idx) => (
            <Button
              key={idx}
              variant={action.variant || 'outline'}
              onClick={action.onClick}
              disabled={action.disabled}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default PageHeader;

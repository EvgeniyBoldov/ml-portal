/**
 * AdminPage - Unified page layout for admin panel
 * 
 * Structure:
 * ┌─────────────────────────────────────────────────────────┐
 * │ [Title + Subtitle]          [Controls] [Search] [Actions] │
 * ├─────────────────────────────────────────────────────────┤
 * │                                                         │
 * │                      Content                            │
 * │                                                         │
 * └─────────────────────────────────────────────────────────┘
 * 
 * Usage:
 * <AdminPage
 *   title="Модели"
 *   subtitle="Управление LLM и Embedding моделями"
 *   searchValue={search}
 *   onSearchChange={setSearch}
 *   actions={[{ label: 'Добавить', onClick: ..., variant: 'primary' }]}
 * >
 *   <DataTable ... />
 * </AdminPage>
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../Button';
import Input from '../Input';
import styles from './AdminPage.module.css';

export interface AdminPageAction {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'outline' | 'ghost' | 'danger';
  disabled?: boolean;
}

export interface AdminPageProps {
  title: string;
  subtitle?: string;
  backTo?: string;
  
  // Search (optional - only show if onSearchChange provided)
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  
  // Actions (buttons on the right)
  actions?: AdminPageAction[];
  
  // Custom controls between title and search (filters, etc)
  // Only rendered if provided
  controls?: React.ReactNode;
  
  // Content
  children: React.ReactNode;
}

export function AdminPage({
  title,
  subtitle,
  backTo,
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Поиск...',
  actions = [],
  controls,
  children,
}: AdminPageProps) {
  const navigate = useNavigate();

  const hasControls = controls || onSearchChange || actions.length > 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleSection}>
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

        {hasControls && (
          <div className={styles.controls}>
            {controls}
            
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
        )}
      </header>

      <div className={styles.content}>
        {children}
      </div>
    </div>
  );
}

export default AdminPage;

/**
 * EntityPage - Unified component for View/Edit/Create entity pages
 * 
 * Supports three modes:
 * - view: readonly display with "Редактировать" button
 * - edit: editable fields with Save/Cancel buttons
 * - create: same as edit but for new entities
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../Button';
import { Icon } from '../Icon';
import styles from './EntityPage.module.css';

export type EntityPageMode = 'view' | 'edit' | 'create';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface EntityPageProps {
  /** Page mode */
  mode: EntityPageMode;
  /** Entity name (e.g., "admins" for tenant) */
  entityName: string;
  /** Entity type label (e.g., "тенант", "пользователь") */
  entityTypeLabel: string;
  /** Back navigation path */
  backPath: string;
  /** Loading state */
  loading?: boolean;
  /** Saving state */
  saving?: boolean;
  /** Switch to edit mode */
  onEdit?: () => void;
  /** Save changes */
  onSave?: () => void;
  /** Cancel editing */
  onCancel?: () => void;
  /** Delete entity */
  onDelete?: () => void;
  /** Show delete button */
  showDelete?: boolean;
  /** Content */
  children: React.ReactNode;
  /** Additional actions in header */
  headerActions?: React.ReactNode;
  /** Breadcrumbs for navigation */
  breadcrumbs?: BreadcrumbItem[];
}

export function EntityPage({
  mode,
  entityName,
  entityTypeLabel,
  backPath,
  loading = false,
  saving = false,
  onEdit,
  onSave,
  onCancel,
  onDelete,
  showDelete = false,
  children,
  headerActions,
  breadcrumbs,
}: EntityPageProps) {
  const navigate = useNavigate();

  const getTitle = () => {
    switch (mode) {
      case 'create':
        return `Создание ${entityTypeLabel}`;
      case 'edit':
        return `Редактирование ${entityTypeLabel}`;
      default:
        return entityName;
    }
  };

  const getSubtitle = () => {
    switch (mode) {
      case 'create':
        return 'Заполните данные для создания';
      case 'edit':
        return entityName;
      default:
        return entityTypeLabel;
    }
  };

  const handleBack = () => {
    if (mode === 'edit' && onCancel) {
      onCancel();
    } else {
      navigate(backPath);
    }
  };

  return (
    <div className={styles.wrap}>
      {/* Breadcrumbs */}
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className={styles.breadcrumbs}>
          {breadcrumbs.map((item, idx) => (
            <React.Fragment key={idx}>
              {item.href ? (
                <a href={item.href} onClick={(e) => {
                  e.preventDefault();
                  navigate(item.href!);
                }}>
                  {item.label}
                </a>
              ) : (
                <span>{item.label}</span>
              )}
              {idx < breadcrumbs.length - 1 && <span className={styles.separator}>/</span>}
            </React.Fragment>
          ))}
        </nav>
      )}

      {/* Content Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <button 
            className={styles.backButton} 
            onClick={handleBack}
            title="Назад"
          >
            <Icon name="arrow-left" size={20} />
          </button>
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>{getTitle()}</h1>
            <span className={styles.subtitle}>{getSubtitle()}</span>
          </div>
          {mode === 'edit' && (
            <span className={styles.editBadge}>Режим редактирования</span>
          )}
        </div>

        <div className={styles.headerRight}>
          {headerActions}
          
          {mode === 'view' && onEdit && (
            <Button variant="primary" onClick={onEdit}>
              Редактировать
            </Button>
          )}

          {mode === 'edit' && (
            <>
              <Button variant="outline" onClick={onCancel} disabled={saving}>
                Отмена
              </Button>
              <Button variant="primary" onClick={onSave} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>
            </>
          )}

          {mode === 'create' && (
            <>
              <Button variant="outline" onClick={() => navigate(backPath)}>
                Отмена
              </Button>
              <Button variant="primary" onClick={onSave} disabled={saving}>
                {saving ? 'Создание...' : 'Создать'}
              </Button>
            </>
          )}

          {showDelete && mode === 'view' && onDelete && (
            <Button variant="danger" onClick={onDelete}>
              Удалить
            </Button>
          )}
        </div>
      </header>

      {/* Content */}
      <div className={styles.content}>
        {loading ? (
          <div className={styles.loading}>Загрузка...</div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

export default EntityPage;

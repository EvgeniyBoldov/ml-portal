/**
 * VersionActionsBlock - Universal action buttons for entity versions
 * 
 * Handles the complete flow for version status management:
 * - draft → activate + edit
 * - active → set as recommended (if not main) + deactivate (if not main)
 * - inactive → reactivate
 * 
 * Used in version pages and version cards
 */
import React from 'react';
import Button from '../Button';
import styles from './VersionActionsBlock.module.css';

export interface VersionActionsBlockProps {
  /** Entity type for API calls */
  entityType: 'prompt' | 'baseline' | 'policy';
  /** Version data */
  version: {
    id: string;
    version: number;
    status: string;
    created_at: string;
    updated_at?: string;
    notes?: string;
    [key: string]: any;
  };
  /** Is this the recommended/main version? */
  isRecommended: boolean;
  /** On activate version */
  onActivate?: () => void;
  /** On deactivate version */
  onDeactivate?: () => void;
  /** On set as recommended */
  onSetRecommended?: () => void;
  /** On edit version */
  onEdit?: () => void;
  /** Loading states */
  loading?: {
    activate?: boolean;
    deactivate?: boolean;
    setRecommended?: boolean;
  };
  /** Additional CSS class */
  className?: string;
}

export function VersionActionsBlock({
  entityType,
  version,
  isRecommended,
  onActivate,
  onDeactivate,
  onSetRecommended,
  onEdit,
  loading = {},
  className = '',
}: VersionActionsBlockProps) {
  const getActions = () => {
    const actions = [];
    
    switch (version.status) {
      case 'draft':
        // Draft: Can activate and edit
        actions.push(
          <Button
            key="activate"
            variant="primary"
            onClick={onActivate}
            disabled={loading.activate}
            loading={loading.activate}
          >
            Активировать
          </Button>
        );
        
        if (onEdit) {
          actions.push(
            <Button
              key="edit"
              variant="outline"
              onClick={onEdit}
            >
              Редактировать
            </Button>
          );
        }
        break;
        
      case 'active':
        // Active: Can set as recommended (if not main) and deactivate (if not main)
        if (!isRecommended && onSetRecommended) {
          actions.push(
            <Button
              key="setRecommended"
              variant="outline"
              onClick={onSetRecommended}
              disabled={loading.setRecommended}
              loading={loading.setRecommended}
            >
              Сделать основной
            </Button>
          );
        }
        
        if (!isRecommended && onDeactivate) {
          actions.push(
            <Button
              key="deactivate"
              variant="danger"
              onClick={onDeactivate}
              disabled={loading.deactivate}
              loading={loading.deactivate}
            >
              Деактивировать
            </Button>
          );
        }
        
        // Note: Active versions cannot be edited (read-only)
        break;
        
      case 'inactive':
        // Inactive: Can reactivate
        if (onActivate) {
          actions.push(
            <Button
              key="reactivate"
              variant="primary"
              onClick={onActivate}
              disabled={loading.activate}
              loading={loading.activate}
            >
              Активировать
            </Button>
          );
        }
        break;
        
      default:
        // Unknown status - no actions
        break;
    }
    
    return actions;
  };

  const actions = getActions();
  
  if (actions.length === 0) {
    return (
      <div className={`${styles.versionActionsBlock} ${className}`}>
        <div className={styles.noActions}>
          {isRecommended ? (
            <span className={styles.mainBadge}>Основная версия</span>
          ) : (
            <span className={styles.noActionsText}>Нет доступных действий</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.versionActionsBlock} ${className}`}>
      <div className={styles.actionsHeader}>
        <span className={styles.versionTitle}>Версия {version.version}</span>
        {isRecommended && (
          <span className={styles.mainBadge}>Основная</span>
        )}
      </div>
      
      <div className={styles.actionsList}>
        {actions.map((action, index) => (
          <div key={index} className={styles.actionItem}>
            {action}
          </div>
        ))}
      </div>
    </div>
  );
}

export default VersionActionsBlock;

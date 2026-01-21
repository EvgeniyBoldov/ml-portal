/**
 * FieldCard - переиспользуемый компонент для отображения поля с search modes
 */
import React from 'react';
import Badge from './Badge';
import styles from './FieldCard.module.css';

export interface SearchModeOption {
  value: string;
  label: string;
  description?: string;
  icon?: string;
}

interface FieldCardProps {
  name: string;
  type: string;
  required?: boolean;
  searchModes?: string[];
  description?: string;
  onRemove?: () => void;
  className?: string;
}

export function FieldCard({
  name,
  type,
  required = false,
  searchModes = [],
  description,
  onRemove,
  className = '',
}: FieldCardProps) {
  const getTypeColor = (fieldType: string) => {
    switch (fieldType) {
      case 'text':
        return 'info';
      case 'integer':
      case 'float':
        return 'success';
      case 'boolean':
        return 'warning';
      case 'date':
      case 'datetime':
        return 'neutral';
      default:
        return 'neutral';
    }
  };

  const getSearchModeIcon = (mode: string) => {
    switch (mode) {
      case 'exact':
        return '=';
      case 'like':
        return '≈';
      case 'range':
        return '⟷';
      case 'vector':
        return '🔍';
      default:
        return '';
    }
  };

  return (
    <div className={`${styles.card} ${className}`}>
      <div className={styles.header}>
        <div className={styles.nameRow}>
          <code className={styles.name}>{name}</code>
          {required && <Badge tone="warning" size="small">Required</Badge>}
        </div>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className={styles.removeBtn}
            aria-label="Remove field"
          >
            ×
          </button>
        )}
      </div>

      <div className={styles.body}>
        <div className={styles.meta}>
          <Badge tone={getTypeColor(type)} size="small">
            {type}
          </Badge>
        </div>

        {searchModes.length > 0 && (
          <div className={styles.searchModes}>
            <span className={styles.label}>Search:</span>
            <div className={styles.modesList}>
              {searchModes.map((mode) => (
                <span key={mode} className={styles.mode} title={mode}>
                  <span className={styles.modeIcon}>{getSearchModeIcon(mode)}</span>
                  <span className={styles.modeLabel}>{mode}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {description && (
          <p className={styles.description}>{description}</p>
        )}
      </div>
    </div>
  );
}

export default FieldCard;

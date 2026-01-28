/**
 * ContentBlock - Universal block component for EntityPage
 * 
 * Supports:
 * - Width: 1/3, 1/2, 2/3, full
 * - Content types: fields, table, multiselect, custom
 * - View/Edit modes
 */
import React from 'react';
import { Icon } from '../Icon';
import Input from '../Input';
import Textarea from '../Textarea';
import Switch from '../Switch';
import Select from '../Select';
import Badge from '../Badge';
import styles from './ContentBlock.module.css';

export type BlockWidth = '1/3' | '1/2' | '2/3' | 'full';

export type FieldType = 
  | 'text' 
  | 'textarea' 
  | 'number' 
  | 'boolean' 
  | 'select' 
  | 'badge' 
  | 'code'
  | 'date'
  | 'custom';

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldDefinition {
  /** Field key in data object */
  key: string;
  /** Display label */
  label: string;
  /** Optional description/hint */
  description?: string;
  /** Field type */
  type: FieldType;
  /** Required field marker */
  required?: boolean;
  /** Options for select type */
  options?: FieldOption[];
  /** Placeholder for input */
  placeholder?: string;
  /** Rows for textarea */
  rows?: number;
  /** Badge tone for badge type */
  badgeTone?: 'info' | 'success' | 'warning' | 'danger' | 'neutral';
  /** Custom render function */
  render?: (value: any, isEditable: boolean, onChange: (value: any) => void) => React.ReactNode;
  /** Disabled in edit mode */
  disabled?: boolean;
}

export interface ContentBlockProps {
  /** Block width */
  width?: BlockWidth;
  /** Header title */
  title: string;
  /** Header icon */
  icon?: string;
  /** Icon color variant */
  iconVariant?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
  /** Is content editable */
  editable?: boolean;
  /** Field definitions for fields content type */
  fields?: FieldDefinition[];
  /** Data object with field values */
  data?: Record<string, any>;
  /** Change handler for field values */
  onChange?: (key: string, value: any) => void;
  /** Custom content (overrides fields) */
  children?: React.ReactNode;
  /** Additional header actions */
  headerActions?: React.ReactNode;
  /** Additional CSS class */
  className?: string;
  /** Compact mode - less padding */
  compact?: boolean;
}

const widthToSpan: Record<BlockWidth, number> = {
  '1/3': 4,
  '1/2': 6,
  '2/3': 8,
  'full': 12,
};

export function ContentBlock({
  width = 'full',
  title,
  icon,
  iconVariant = 'primary',
  editable = false,
  fields,
  data = {},
  onChange,
  children,
  headerActions,
  className = '',
  compact = false,
}: ContentBlockProps) {
  const spanClass = `span-${widthToSpan[width]}`;

  const handleChange = (key: string, value: any) => {
    onChange?.(key, value);
  };

  const renderFieldValue = (field: FieldDefinition) => {
    const value = data[field.key];
    const isDisabled = field.disabled || !editable;

    // Custom render
    if (field.render) {
      return field.render(value, editable && !field.disabled, (v) => handleChange(field.key, v));
    }

    // View mode
    if (!editable) {
      switch (field.type) {
        case 'boolean':
          return (
            <Switch checked={!!value} onChange={() => {}} disabled />
          );
        case 'badge':
          return value ? (
            <Badge tone={field.badgeTone || 'neutral'}>{String(value)}</Badge>
          ) : (
            <span className={styles.emptyValue}>—</span>
          );
        case 'code':
          return (
            <code className={styles.codeValue}>{value || '—'}</code>
          );
        case 'select':
          const option = field.options?.find(o => o.value === value);
          return (
            <div className={styles.fieldValue}>{option?.label || value || '—'}</div>
          );
        default:
          return (
            <div className={styles.fieldValue}>{value || '—'}</div>
          );
      }
    }

    // Edit mode
    switch (field.type) {
      case 'text':
      case 'number':
        return (
          <Input
            type={field.type === 'number' ? 'number' : 'text'}
            value={value ?? ''}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleChange(field.key, e.target.value)}
            placeholder={field.placeholder}
            disabled={isDisabled}
          />
        );
      case 'textarea':
        return (
          <Textarea
            value={value ?? ''}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => handleChange(field.key, e.target.value)}
            placeholder={field.placeholder}
            rows={field.rows || 3}
            disabled={isDisabled}
          />
        );
      case 'boolean':
        return (
          <Switch
            checked={!!value}
            onChange={(checked) => handleChange(field.key, checked)}
            disabled={isDisabled}
          />
        );
      case 'select':
        return (
          <Select
            value={value ?? ''}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => handleChange(field.key, e.target.value)}
            disabled={isDisabled}
          >
            <option value="">Выберите...</option>
            {field.options?.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
        );
      case 'badge':
        return value ? (
          <Badge tone={field.badgeTone || 'neutral'}>{String(value)}</Badge>
        ) : (
          <span className={styles.emptyValue}>—</span>
        );
      case 'code':
        return (
          <Input
            value={value ?? ''}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleChange(field.key, e.target.value)}
            placeholder={field.placeholder}
            disabled={isDisabled}
            className={styles.codeInput}
          />
        );
      default:
        return (
          <div className={styles.fieldValue}>{value || '—'}</div>
        );
    }
  };

  const renderField = (field: FieldDefinition) => {
    // Boolean fields render inline (row layout)
    if (field.type === 'boolean') {
      return (
        <div key={field.key} className={styles.fieldRow}>
          <div className={styles.fieldRowLabel}>
            <span className={styles.fieldTitle}>{field.label}</span>
            {field.description && (
              <span className={styles.fieldDescription}>{field.description}</span>
            )}
          </div>
          {renderFieldValue(field)}
        </div>
      );
    }

    // Other fields render stacked
    return (
      <div key={field.key} className={styles.fieldGroup}>
        <label className={`${styles.fieldLabel} ${field.required ? styles.required : ''}`}>
          {field.label}
        </label>
        {renderFieldValue(field)}
        {field.description && editable && (
          <span className={styles.fieldHint}>{field.description}</span>
        )}
      </div>
    );
  };

  return (
    <div 
      className={`${styles.block} ${styles[spanClass]} ${compact ? styles.compact : ''} ${className}`}
      style={{ '--span': widthToSpan[width] } as React.CSSProperties}
    >
      <div className={styles.header}>
        {icon && (
          <div className={`${styles.icon} ${styles[iconVariant]}`}>
            <Icon name={icon} size={18} />
          </div>
        )}
        <h3 className={styles.title}>{title}</h3>
        {headerActions && (
          <div className={styles.headerActions}>{headerActions}</div>
        )}
      </div>
      <div className={styles.content}>
        {children || (
          fields?.map(field => renderField(field))
        )}
      </div>
    </div>
  );
}

export default ContentBlock;

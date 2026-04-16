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
import Toggle from '../Toggle';
import { Select } from '../Select';
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
  badgeTone?: 'info' | 'success' | 'warning' | 'warn' | 'danger' | 'neutral';
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

const FieldEditor = ({
  field,
  value,
  onChange,
  editable,
}: {
  field: FieldDefinition;
  value: any;
  onChange: (value: any) => void;
  editable: boolean;
}) => {
  const isDisabled = !editable || field.disabled;

  switch (field.type) {
    case 'text':
      return (
        <Input
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={isDisabled}
        />
      );
    case 'textarea':
      return (
        <Textarea
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={field.rows || 3}
          disabled={isDisabled}
        />
      );
    case 'boolean':
      return (
        <Toggle
          checked={!!value}
          onChange={(checked) => onChange(checked)}
          disabled={isDisabled}
        />
      );
    case 'select':
      return (
        <Select
          value={value ?? ''}
          onChange={(val) => onChange(val)}
          placeholder="Выберите..."
          options={field.required ? (field.options || []) : [
            { value: '', label: 'Выберите...' },
            ...(field.options || [])
          ]}
          disabled={isDisabled}
        />
      );
    case 'badge':
      return value ? (
        <Badge tone={field.badgeTone === 'warning' ? 'warn' : (field.badgeTone || 'neutral')}>{String(value)}</Badge>
      ) : (
        <span className={styles.emptyValue}>—</span>
      );
    case 'code':
      return (
        <Input
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
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

export function ContentBlock({
  width = 'full',
  title,
  icon,
  iconVariant = 'primary',
  children,
  fields,
  data,
  onChange,
  editable = false,
  headerActions,
  className = '',
  compact = false,
}: ContentBlockProps) {
  const handleChange = (key: string, value: any) => {
    onChange?.(key, value);
  };

  return (
    <div 
      className={`${styles.block} ${styles[`width${width.replace('/', '_')}`]} ${compact ? styles.compact : ''} ${className}`}
    >
      <div className={styles.header}>
        {icon && (
          <div className={`${styles.icon} ${styles[iconVariant]}`}>
            <Icon name={icon} size={18} />
          </div>
        )}
        <h3 className={styles.title}>{title}</h3>
        {headerActions && (
          <div className={styles.headerActions}>
            {headerActions}
          </div>
        )}
      </div>

      <div className={styles.content}>
        {fields && data ? (
          <div className={styles.fields}>
            {fields.map((field) => (
              <div key={field.key} className={styles.fieldRow}>
                <div className={styles.fieldRowLabel}>
                  <div className={styles.fieldTitle}>{field.label}</div>
                  {field.description && (
                    <div className={styles.fieldDescription}>{field.description}</div>
                  )}
                </div>
                <div className={styles.fieldRowValue}>
                  <FieldEditor
                    field={field}
                    value={data[field.key]}
                    onChange={(value) => handleChange(field.key, value)}
                    editable={editable}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

export default ContentBlock;

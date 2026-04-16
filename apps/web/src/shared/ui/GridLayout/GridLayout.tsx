/**
 * GridLayout — Auto-fill grid system for entity pages
 * Block — Universal block container with width/height control
 * 
 * Usage:
 *   <GridLayout>
 *     <Block title="Info" icon="info" width="1/2" fields={fields} data={entity} />
 *     <Block title="Status" width="1/3" height="stretch">
 *       <Badge>Active</Badge>
 *     </Block>
 *     <Block title="Meta" width="auto">
 *       <SomeCustomContent />
 *     </Block>
 *   </GridLayout>
 * 
 * Width must sum to ~1 per row (e.g. 1/2 + 1/2, or 1/3 + 2/3, or full).
 * Height "stretch" fills the row height, "auto" sizes by content.
 */
import React, { useState } from 'react';
import { Icon } from '../Icon';
import Input from '../Input';
import Textarea from '../Textarea';
import Toggle from '../Toggle';
import { Select } from '../Select';
import Badge from '../Badge';
import { Tags } from '../Tags';
import { JSONDisplaySimple } from '../JSONDisplay/JSONDisplaySimple';
import styles from './GridLayout.module.css';

/* ─── Types ─── */

export type BlockWidth = 'full' | '1/2' | '1/3' | '2/3' | '1/4' | '3/4';
export type BlockHeight = 'auto' | 'stretch';
export type IconVariant = 'primary' | 'success' | 'warning' | 'warn' | 'danger' | 'info' | 'neutral';

export type FieldType =
  | 'text'
  | 'password'
  | 'textarea'
  | 'number'
  | 'boolean'
  | 'select'
  | 'badge'
  | 'code'
  | 'json'
  | 'date'
  | 'tags'
  | 'custom';

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldConfig {
  key: string;
  type: FieldType;
  label: string;
  description?: string;
  required?: boolean;
  options?: FieldOption[];
  placeholder?: string;
  rows?: number;
  badgeTone?: 'info' | 'success' | 'warn' | 'danger' | 'neutral';
  disabled?: boolean;
  /** false = always readonly regardless of mode */
  editable?: boolean;
  /** Max tags for type='tags' */
  maxTags?: number;
  /** Custom render for type='custom' */
  render?: (value: any, editable: boolean, onChange: (v: any) => void) => React.ReactNode;
  step?: number;
  min?: number;
  max?: number;
}

/* ─── GridLayout ─── */

export interface GridLayoutProps {
  children: React.ReactNode;
  className?: string;
  gap?: number;
}

export function GridLayout({ children, className = '', gap }: GridLayoutProps) {
  return (
    <div
      className={`${styles.grid} ${className}`}
      style={gap ? { gap: `${gap}px` } : undefined}
    >
      {children}
    </div>
  );
}

/* ─── Block ─── */

export interface BlockProps {
  /** Block title in header */
  title: string;
  /** Icon name (from Icon component) */
  icon?: string;
  /** Icon color variant */
  iconVariant?: IconVariant;
  /** Block width as fraction */
  width?: BlockWidth;
  /** Block height behavior */
  height?: BlockHeight;
  /** Field definitions — renders structured field rows */
  fields?: FieldConfig[];
  /** Data object for field values */
  data?: Record<string, any>;
  /** Edit mode */
  editable?: boolean;
  /** Field change handler */
  onChange?: (key: string, value: any) => void;
  /** Header actions (buttons etc) */
  headerActions?: React.ReactNode;
  /** Compact padding */
  compact?: boolean;
  /** Custom content (used when no fields provided) */
  children?: React.ReactNode;
  /** Additional CSS class on the outer wrapper */
  className?: string;
}

const WIDTH_CLASS: Record<BlockWidth, string> = {
  'full': styles['w-full'],
  '1/2': styles['w-1-2'],
  '1/3': styles['w-1-3'],
  '2/3': styles['w-2-3'],
  '1/4': styles['w-1-4'],
  '3/4': styles['w-3-4'],
};

const HEIGHT_CLASS: Record<BlockHeight, string> = {
  'auto': styles['h-auto'],
  'stretch': styles['h-stretch'],
};

export function Block({
  title,
  icon,
  iconVariant = 'primary',
  width = 'full',
  height = 'auto',
  fields,
  data,
  editable = false,
  onChange,
  headerActions,
  compact = false,
  children,
  className = '',
}: BlockProps) {
  const widthCls = WIDTH_CLASS[width] || WIDTH_CLASS['full'];
  const heightCls = HEIGHT_CLASS[height] || HEIGHT_CLASS['auto'];

  return (
    <div className={`${styles.block} ${widthCls} ${heightCls} ${className}`}>
      <div className={styles.card}>
        {/* Header */}
        <div className={styles['card-header']}>
          {icon && (
            <div className={`${styles['card-icon']} ${styles[iconVariant]}`}>
              <Icon name={icon} size={18} />
            </div>
          )}
          <h3 className={styles['card-title']}>{title}</h3>
          {headerActions && (
            <div className={styles['card-actions']}>
              {headerActions}
            </div>
          )}
        </div>

        {/* Body */}
        <div className={`${styles['card-body']} ${compact ? styles.compact : ''}`}>
          {fields && data ? (
            <FieldRows
              fields={fields}
              data={data}
              editable={editable}
              onChange={onChange}
            />
          ) : (
            children
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── FieldRows — renders field list inside Block ─── */

interface FieldRowsProps {
  fields: FieldConfig[];
  data: Record<string, any>;
  editable: boolean;
  onChange?: (key: string, value: any) => void;
}

function FieldRows({ fields, data, editable, onChange }: FieldRowsProps) {
  return (
    <>
      {fields.map((field) => {
        const isFieldEditable = editable && field.editable !== false && !field.disabled;
        const value = data[field.key];

        return (
          <div key={field.key} className={styles['field-row']}>
            <div className={styles['field-label']}>
              <div className={styles['field-label-text']}>
                {field.label}
                {field.required && <span style={{ color: 'var(--danger, #ef4444)', marginLeft: 4 }}>*</span>}
              </div>
              {field.description && (
                <div className={styles['field-description']}>{field.description}</div>
              )}
            </div>
            <div className={styles['field-value']}>
              <FieldEditor
                field={field}
                value={value}
                editable={isFieldEditable}
                onChange={(v) => onChange?.(field.key, v)}
              />
            </div>
          </div>
        );
      })}
    </>
  );
}

/* ─── FieldEditor — renders individual field by type ─── */

interface FieldEditorProps {
  field: FieldConfig;
  value: any;
  editable: boolean;
  onChange: (value: any) => void;
}

interface PasswordFieldEditorProps {
  value: any;
  editable: boolean;
  placeholder?: string;
  onChange: (value: any) => void;
}

function PasswordFieldEditor({ value, editable, placeholder, onChange }: PasswordFieldEditorProps) {
  const [revealed, setRevealed] = useState(false);
  const text = String(value ?? '');
  const passwordStyle = revealed
    ? undefined
    : ({ WebkitTextSecurity: 'disc' } as React.CSSProperties);

  if (!editable) {
    const masked = text ? '*'.repeat(Math.max(text.length, 3)) : '********';
    return (
      <code style={{
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: '0.875rem',
        color: 'var(--text-secondary)',
        letterSpacing: '0.05em',
      }}>
        {masked}
      </code>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <Input
        type={revealed ? 'text' : 'password'}
        value={text}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        disabled={false}
        style={passwordStyle}
      />
      <button
        type="button"
        onClick={() => setRevealed((prev) => !prev)}
        style={{
          border: '1px solid var(--border)',
          borderRadius: '8px',
          background: 'transparent',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
          padding: '0.35rem 0.5rem',
          lineHeight: 1,
        }}
        title={revealed ? 'Скрыть' : 'Показать'}
      >
        <Icon name={revealed ? 'eye-off' : 'eye'} size={16} />
      </button>
    </div>
  );
}

function FieldEditor({ field, value, editable, onChange }: FieldEditorProps) {
  const isDisabled = !editable;

  switch (field.type) {
    case 'text':
      if (isDisabled) {
        return <div className={styles['field-empty']}>{value || '—'}</div>;
      }
      return (
        <Input
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={false}
        />
      );

    case 'password': {
      return (
        <PasswordFieldEditor
          value={value}
          editable={!isDisabled}
          placeholder={field.placeholder}
          onChange={onChange}
        />
      );
    }

    case 'textarea':
      if (isDisabled) {
        return <div className={styles['field-empty']} style={{ whiteSpace: 'pre-wrap' }}>{value || '—'}</div>;
      }
      return (
        <Textarea
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={field.rows || 3}
          disabled={false}
        />
      );

    case 'number':
      if (isDisabled) {
        return <div className={styles['field-empty']}>{value ?? '—'}</div>;
      }
      return (
        <Input
          type="number"
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(Number(e.target.value) || 0)}
          placeholder={field.placeholder}
          disabled={false}
          step={field.step}
          min={field.min}
          max={field.max}
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
      if (isDisabled) {
        const selectedLabel = field.options?.find(o => o.value === value)?.label || value || '—';
        return <div className={styles['field-empty']}>{selectedLabel}</div>;
      }
      return (
        <Select
          value={value ?? ''}
          onChange={(val) => onChange(val)}
          placeholder="Выберите..."
          options={field.options || []}
          disabled={false}
        />
      );

    case 'badge':
      return value != null ? (
        <Badge tone={field.badgeTone || 'neutral'}>{String(value)}</Badge>
      ) : (
        <div className={styles['field-empty']}>—</div>
      );

    case 'code':
      if (isDisabled) {
        return (
          <code style={{
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: '0.875rem',
            color: 'var(--text-secondary)',
          }}>
            {value || '—'}
          </code>
        );
      }
      return (
        <Input
          value={value ?? ''}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={false}
          style={{ fontFamily: 'var(--font-mono, monospace)' }}
        />
      );

    case 'json': {
      const jsonValue = typeof value === 'string'
        ? value
        : JSON.stringify(value ?? {}, null, 2);

      if (isDisabled) {
        return <JSONDisplaySimple value={jsonValue} maxHeight="320px" />;
      }

      return (
        <Textarea
          value={jsonValue}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
            const raw = e.target.value;
            try {
              onChange(JSON.parse(raw));
            } catch {
              onChange(raw);
            }
          }}
          placeholder={field.placeholder}
          rows={field.rows || 8}
          disabled={false}
        />
      );
    }

    case 'date':
      if (!value) return <div className={styles['field-empty']}>—</div>;
      const formatted = new Date(value).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
      return (
        <code style={{
          fontFamily: 'var(--font-mono, monospace)',
          fontSize: '0.875rem',
          color: 'var(--text-secondary)',
        }}>
          {formatted}
        </code>
      );

    case 'tags': {
      const tags: string[] = Array.isArray(value)
        ? value
        : (typeof value === 'string' && value ? value.split(',').map((t: string) => t.trim()).filter(Boolean) : []);
      return (
        <Tags
          value={tags}
          onChange={(newTags: string[]) => onChange(newTags)}
          disabled={isDisabled}
          placeholder={field.placeholder}
        />
      );
    }

    case 'custom':
      if (field.render) {
        return <>{field.render(value, editable, onChange)}</>;
      }
      return <div className={styles['field-empty']}>—</div>;

    default:
      return <div className={styles['field-empty']}>{value ?? '—'}</div>;
  }
}

export default GridLayout;

import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import Badge from '../Badge';
import { Icon } from '../Icon';
import type { ResponseContract } from '@/shared/api/admin';
import styles from './ContractAwareEditor.module.css';

type SchemaNodeProps = {
  schema: Record<string, unknown>;
  coverageMap?: Map<string, boolean>;
  basePath?: string;
  depth?: number;
  required?: boolean;
  onFieldClick?: (fieldName: string) => void;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function normalizeType(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string').join(' | ');
  return 'object';
}

function typeTone(type: string): 'info' | 'success' | 'warn' | 'danger' | 'neutral' {
  if (type.includes('string')) return 'info';
  if (type.includes('array')) return 'success';
  if (type.includes('object')) return 'warn';
  if (type.includes('boolean')) return 'neutral';
  if (type.includes('integer') || type.includes('number')) return 'danger';
  return 'neutral';
}

function NodeRow({
  label,
  path,
  schema,
  coverageMap,
  depth = 0,
  required = false,
  onFieldClick,
}: {
  label: string;
  path: string;
  schema: Record<string, unknown>;
  coverageMap?: Map<string, boolean>;
  depth?: number;
  required?: boolean;
  onFieldClick?: (fieldName: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const type = normalizeType(schema.type);
  const hasChildren = Boolean(schema.properties) || Boolean(schema.oneOf) || Boolean(schema.items);
  const isRequired = required;
  const conditional = typeof schema.x_when === 'string' ? schema.x_when : '';
  const description = typeof schema.description === 'string' ? schema.description : '';
  const enumValues = asStringArray(schema.enum);
  const covered = coverageMap?.get(path) ?? false;

  const indentStyle = useMemo(() => ({ paddingLeft: `${depth * 14}px` }), [depth]);

  return (
    <div className={styles.schemaNode} style={indentStyle}>
      <button
        type="button"
        className={styles.schemaSummary}
        onClick={() => {
          if (hasChildren) setOpen((prev) => !prev);
          onFieldClick?.(path);
        }}
      >
        <span className={styles.schemaName}>
          {hasChildren && <Icon name={open ? 'chevron-down' : 'chevron-right'} size={14} />}
          <code>{label}</code>
        </span>
        <span className={styles.schemaMeta}>
          <Badge tone={typeTone(type)} size="small">{type}</Badge>
          {isRequired && <Badge tone="danger" size="small">*</Badge>}
          {conditional && <Badge tone="warn" size="small">{conditional}</Badge>}
          {coverageMap && <Badge tone={covered ? 'success' : 'warn'} size="small">{covered ? '✓' : '⚠'}</Badge>}
        </span>
      </button>
      {description && <div className={styles.schemaDescription}>{description}</div>}
      {enumValues.length > 0 && (
        <div className={styles.schemaEnum}>
          {enumValues.slice(0, 5).join(' | ')}
          {enumValues.length > 5 ? ' ...' : ''}
        </div>
      )}
      {hasChildren && open && (
        <div className={styles.schemaChildren}>
          {renderChildren(schema, path, depth + 1, coverageMap, onFieldClick)}
        </div>
      )}
    </div>
  );
}

function renderChildren(
  schema: Record<string, unknown>,
  basePath: string,
  depth: number,
  coverageMap?: Map<string, boolean>,
  onFieldClick?: (fieldName: string) => void,
) {
  const nodes: ReactNode[] = [];
  const requiredSet = new Set(asStringArray(schema.required));
  const properties = asRecord(schema.properties);
  for (const [key, raw] of Object.entries(properties)) {
    const child = asRecord(raw);
    const path = basePath ? `${basePath}.${key}` : key;
    nodes.push(
      <NodeRow
        key={path}
        label={key}
        path={path}
        schema={child}
        coverageMap={coverageMap}
        depth={depth}
        required={requiredSet.has(key)}
        onFieldClick={onFieldClick}
      />,
    );
  }

  const items = asRecord(schema.items);
  if (Object.keys(items).length > 0) {
    nodes.push(
      <NodeRow
        key={`${basePath}[]`}
        label="[]"
        path={`${basePath}[]`}
        schema={items}
        coverageMap={coverageMap}
        depth={depth}
        required={requiredSet.has(basePath.replace(/\[\]$/, ''))}
        onFieldClick={onFieldClick}
      />,
    );
  }

  return nodes;
}

export function SchemaTreeRenderer({
  schema,
  coverageMap,
  basePath = '',
  depth = 0,
  onFieldClick,
}: SchemaNodeProps) {
  const properties = asRecord(schema.properties);
  const items = asRecord(schema.items);

  if (Object.keys(properties).length === 0 && Object.keys(items).length === 0) {
    return null;
  }

  return (
    <div className={styles.schemaTree}>
      {renderChildren(schema, basePath, depth, coverageMap, onFieldClick)}
    </div>
  );
}

export function ResponseContractSchemaSummary({
  contract,
  coverageMap,
  onFieldClick,
}: {
  contract: ResponseContract | null;
  coverageMap?: Map<string, boolean>;
  onFieldClick?: (fieldName: string) => void;
}) {
  if (!contract || contract.format !== 'json') return null;
  const schema = asRecord(contract.schema);
  const variants = Array.isArray(schema.oneOf) ? schema.oneOf : [];

  return (
    <div className={styles.legendSection}>
      {variants.length > 0 && (
        <details open className={styles.legendDetails}>
          <summary className={styles.legendSummary}>Варианты ответа</summary>
          <div className={styles.legendBody}>
            {variants.map((variant, index) => {
              const variantSchema = asRecord(variant);
              const title = typeof variantSchema.title === 'string' && variantSchema.title.trim().length > 0
                ? variantSchema.title
                : `variant-${index + 1}`;
              const kindSchema = asRecord(asRecord(variantSchema.properties).kind);
              const kind = typeof kindSchema.const === 'string'
                ? kindSchema.const
                : asStringArray(kindSchema.enum).join(' | ') || '—';
              return (
                <details key={title} open={index === 0} className={styles.variantCard}>
                  <summary className={styles.variantSummary}>
                    <span>{title}</span>
                    <Badge tone="info" size="small">kind={kind}</Badge>
                  </summary>
                  <div className={styles.variantBody}>
                    {asStringArray(variantSchema.required).length > 0 && (
                      <div className={styles.legendList}>
                        {asStringArray(variantSchema.required).map((field) => (
                          <button
                            key={`${title}.${field}`}
                            type="button"
                            className={styles.legendFieldButton}
                            onClick={() => onFieldClick?.(`${title}.${field}`)}
                          >
                            <code>{field}</code>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </details>
              );
            })}
          </div>
        </details>
      )}

      <details open className={styles.legendDetails}>
        <summary className={styles.legendSummary}>Поля ответа</summary>
        <div className={styles.legendBody}>
          <SchemaTreeRenderer
            schema={schema}
            coverageMap={coverageMap}
            onFieldClick={onFieldClick}
          />
        </div>
      </details>
    </div>
  );
}

export function PlainTextContractLegend({
  contract,
}: {
  contract: ResponseContract | null;
}) {
  if (!contract) return null;
  const textContract = contract.format === 'plain_text' ? contract.plain_text : contract.markdown;
  if (!textContract || typeof textContract !== 'object') return null;
  const criteria = asStringArray((textContract as Record<string, unknown>).criteria);
  const forbidden = asStringArray((textContract as Record<string, unknown>).forbidden);

  return (
    <div className={styles.legendSection}>
      {criteria.length > 0 && (
        <div className={styles.legendGroup}>
          <div className={styles.legendGroupTitle}>Что можно</div>
          <div className={styles.legendChecklist}>
            {criteria.map((item) => (
              <div key={item} className={styles.legendChecklistItem}>
                <Badge tone="success" size="small">ok</Badge>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {forbidden.length > 0 && (
        <div className={styles.legendGroup}>
          <div className={styles.legendGroupTitle}>Что нельзя</div>
          <div className={styles.legendChecklist}>
            {forbidden.map((item) => (
              <div key={item} className={styles.legendChecklistItem}>
                <Badge tone="danger" size="small">no</Badge>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

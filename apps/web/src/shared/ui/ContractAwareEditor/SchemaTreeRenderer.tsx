import { useMemo, useState } from 'react';
import { useEffect, useRef } from 'react';

import type { ResponseContract } from '@/shared/api/admin';
import styles from './ContractAwareEditor.module.css';

type RenderNode = {
  key: string;
  name: string;
  path: string;
  typeLabel: string;
  required: boolean;
  description: string;
  enumValues: string[];
  condition: string;
  children: RenderNode[];
};

const HIDDEN_FIELDS = new Set(['kind', 'rationale']);
const MAX_RECURSION_DEPTH = 4;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function normalizeType(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    const filtered = value.filter((item): item is string => typeof item === 'string');
    return filtered.join(' | ');
  }
  return 'object';
}

function buildChildren(
  schema: Record<string, unknown>,
  basePath: string,
  depth: number,
  inheritedRequired = false,
): RenderNode[] {
  if (depth > MAX_RECURSION_DEPTH) return [];
  const result: RenderNode[] = [];
  const properties = asRecord(schema.properties);
  const requiredSet = new Set(asStringArray(schema.required));

  for (const [name, rawChild] of Object.entries(properties)) {
    if (HIDDEN_FIELDS.has(name)) continue;
    const child = asRecord(rawChild);
    const path = basePath ? `${basePath}.${name}` : name;
    const typeLabel = normalizeType(child.type);
    const childNodes: RenderNode[] = [];

    if (Object.keys(asRecord(child.properties)).length > 0) {
      childNodes.push(...buildChildren(child, path, depth + 1, inheritedRequired || requiredSet.has(name)));
    }

    const items = asRecord(child.items);
    if (Object.keys(items).length > 0) {
      const itemType = normalizeType(items.type);
      const itemPath = `${path}[]`;
      const itemChildren =
        Object.keys(asRecord(items.properties)).length > 0
          ? buildChildren(items, itemPath, depth + 1, inheritedRequired || requiredSet.has(name))
          : [];
      childNodes.push({
        key: `${itemPath}-items`,
        name: 'items[]',
        path: itemPath,
        typeLabel: itemType,
        required: inheritedRequired || requiredSet.has(name),
        description: typeof items.description === 'string' ? items.description : '',
        enumValues: asStringArray(items.enum),
        condition: typeof items.x_when === 'string' ? items.x_when : '',
        children: itemChildren,
      });
    }

    result.push({
      key: path,
      name,
      path,
      typeLabel,
      required: inheritedRequired || requiredSet.has(name),
      description: typeof child.description === 'string' ? child.description : '',
      enumValues: asStringArray(child.enum),
      condition: typeof child.x_when === 'string' ? child.x_when : '',
      children: childNodes,
    });
  }

  return result;
}

function NodeRow({
  node,
  depth,
  coverageMap,
  showCoverage,
  onInsert,
  onHoverField,
  activeField,
}: {
  node: RenderNode;
  depth: number;
  coverageMap?: Map<string, boolean>;
  showCoverage: boolean;
  onInsert?: (token: string) => void;
  onHoverField?: (fieldName: string | null) => void;
  activeField?: string | null;
}) {
  const hasChildren = node.children.length > 0;
  const [open, setOpen] = useState(depth < 1);
  const covered = coverageMap?.get(node.path) ?? false;
  const indent = useMemo(() => ({ marginLeft: `${depth * 14}px` }), [depth]);
  const rowRef = useRef<HTMLDivElement>(null);
  const isActive = Boolean(activeField && activeField === node.name);

  useEffect(() => {
    if (!isActive) return;
    rowRef.current?.scrollIntoView({ block: 'nearest' });
  }, [isActive]);

  return (
    <div
      ref={rowRef}
      className={`${styles.fieldRow} ${isActive ? styles.fieldRowActive : ''}`}
      style={indent}
      data-field={node.name}
    >
      <div className={styles.fieldRowMain}>
        {hasChildren ? (
          <button type="button" className={styles.expandNodeBtn} onClick={() => setOpen((v: boolean) => !v)} title={open ? 'Свернуть' : 'Развернуть'}>
            {open ? '▾' : '▸'}
          </button>
        ) : (
          <span className={styles.expandNodeSpacer} />
        )}
        <button type="button" className={styles.fieldName} onClick={() => onInsert?.(node.name)} title="Вставить имя поля">
          <span
            onMouseEnter={() => onHoverField?.(node.name)}
            onMouseLeave={() => onHoverField?.(null)}
          >
          {node.name}
          </span>
        </button>
        {node.required ? <span className={styles.fieldRequired}>*</span> : null}
        <span className={styles.fieldType}>{node.typeLabel}</span>
        {node.condition ? <span className={styles.fieldCondition}>{node.condition}</span> : null}
        {showCoverage ? (
          <span className={`${styles.fieldCoverage} ${covered ? styles.fieldCoverageCovered : styles.fieldCoverageUncovered}`}>
            {covered ? '✓' : '⚠'}
          </span>
        ) : null}
      </div>

      {node.description ? <div className={styles.fieldDescription}>{node.description}</div> : null}
      {node.enumValues.length > 0 ? (
        <div className={styles.enumChips}>
          {node.enumValues.slice(0, 5).map((val) => (
            <button key={`${node.path}-${val}`} type="button" className={styles.enumChip} onClick={() => onInsert?.(val)} title={`Вставить "${val}"`}>
              {val}
            </button>
          ))}
        </div>
      ) : null}

      {hasChildren && open ? (
        <div className={styles.fieldChildren}>
          {node.children.map((child) => (
            <NodeRow key={child.key} node={child} depth={depth + 1} coverageMap={coverageMap} showCoverage={showCoverage} onInsert={onInsert} onHoverField={onHoverField} activeField={activeField} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function SchemaTreeRenderer({
  schema,
  coverageMap,
  showCoverage = false,
  onInsert,
  onHoverField,
  activeField,
}: {
  schema: Record<string, unknown>;
  coverageMap?: Map<string, boolean>;
  showCoverage?: boolean;
  onInsert?: (token: string) => void;
  onHoverField?: (fieldName: string | null) => void;
  activeField?: string | null;
}) {
  const nodes = useMemo(() => buildChildren(schema, '', 0), [schema]);
  if (nodes.length === 0) return null;
  return (
    <div className={styles.legendSection}>
      {nodes.map((node) => (
        <NodeRow key={node.key} node={node} depth={0} coverageMap={coverageMap} showCoverage={showCoverage} onInsert={onInsert} onHoverField={onHoverField} activeField={activeField} />
      ))}
    </div>
  );
}

export function ResponseContractSchemaSummary({
  contract,
  coverageMap,
  onInsert,
  onHoverField,
  activeField,
}: {
  contract: ResponseContract | null;
  coverageMap?: Map<string, boolean>;
  onInsert?: (token: string) => void;
  onHoverField?: (fieldName: string | null) => void;
  activeField?: string | null;
}) {
  if (!contract || contract.format !== 'json') return null;
  const schema = asRecord(contract.schema);
  const oneOf = Array.isArray(schema.oneOf) ? schema.oneOf : [];

  if (oneOf.length === 0) {
    return <SchemaTreeRenderer schema={schema} coverageMap={coverageMap} showCoverage onInsert={onInsert} onHoverField={onHoverField} activeField={activeField} />;
  }

  return (
    <div className={styles.legendSection}>
      {oneOf.map((variant, index) => {
        const variantSchema = asRecord(variant);
        const title = typeof variantSchema.title === 'string' && variantSchema.title.trim().length > 0
          ? variantSchema.title
          : `variant-${index + 1}`;
        const variantKinds = getVariantKinds(variantSchema);
        const filteredProperties = filterPropertiesByVariant(
          asRecord(schema.properties),
          asRecord(variantSchema.properties),
          variantKinds,
        );
        const merged: Record<string, unknown> = {
          ...schema,
          properties: filteredProperties,
          required: [...new Set([...asStringArray(schema.required), ...asStringArray(variantSchema.required)])],
        };
        return (
          <details key={title} open={index === 0} className={styles.variantCard}>
            <summary className={styles.variantSummary}>
              <span>{title}</span>
              <span className={styles.variantChevron}>▶</span>
            </summary>
            <div className={styles.variantBody}>
              <SchemaTreeRenderer schema={merged} coverageMap={coverageMap} showCoverage onInsert={onInsert} onHoverField={onHoverField} activeField={activeField} />
            </div>
          </details>
        );
      })}
    </div>
  );
}

function getVariantKinds(variantSchema: Record<string, unknown>): Set<string> {
  const kindProp = asRecord(asRecord(variantSchema.properties).kind);
  if (typeof kindProp.const === 'string') return new Set([kindProp.const]);
  const enumVals = asStringArray(kindProp.enum);
  return new Set(enumVals);
}

function parseXWhenKinds(value: string): Set<string> {
  const match = /^kind\s*=\s*(.+)$/.exec(value.trim());
  if (!match) return new Set();
  return new Set(match[1].split('|').map((s) => s.trim()).filter(Boolean));
}

function filterPropertiesByVariant(
  topProperties: Record<string, unknown>,
  variantProperties: Record<string, unknown>,
  variantKinds: Set<string>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  // Variant-specific properties always included (e.g. kind discriminator override)
  for (const [key, value] of Object.entries(variantProperties)) {
    result[key] = value;
  }
  for (const [key, rawValue] of Object.entries(topProperties)) {
    if (key in result) continue;
    const propSchema = asRecord(rawValue);
    const xWhen = typeof propSchema.x_when === 'string' ? propSchema.x_when.trim() : '';
    if (!xWhen) {
      // No condition → field is shared, applies to every variant
      result[key] = rawValue;
      continue;
    }
    if (variantKinds.size === 0) {
      // Variant has no discriminator → can't filter, include conservatively
      result[key] = rawValue;
      continue;
    }
    const requiredKinds = parseXWhenKinds(xWhen);
    if (requiredKinds.size === 0) {
      // Unknown x_when format → include conservatively
      result[key] = rawValue;
      continue;
    }
    for (const kind of requiredKinds) {
      if (variantKinds.has(kind)) {
        result[key] = rawValue;
        break;
      }
    }
  }
  return result;
}

export function PlainTextContractLegend({
  contract,
}: {
  contract: ResponseContract | null;
}) {
  if (!contract) return null;
  const plain = contract.format === 'plain_text' ? contract.plain_text : contract.markdown;
  if (!plain || typeof plain !== 'object') return null;
  const criteria = asStringArray((plain as Record<string, unknown>).criteria);
  const forbidden = asStringArray((plain as Record<string, unknown>).forbidden);
  if (criteria.length === 0 && forbidden.length === 0) return null;

  return (
    <div className={styles.safetyFooter}>
      {criteria.length > 0 ? (
        <div className={styles.safetyGroup}>
          <div className={styles.safetyTitle}>Safety criteria</div>
          {criteria.map((item) => <div key={item} className={styles.safetyItem}>• {item}</div>)}
        </div>
      ) : null}
      {forbidden.length > 0 ? (
        <div className={styles.safetyGroup}>
          <div className={styles.safetyTitle}>Forbidden</div>
          {forbidden.map((item) => <div key={item} className={styles.safetyItem}>• {item}</div>)}
        </div>
      ) : null}
    </div>
  );
}

import type { ReactNode } from 'react';
import type { TemplateSchemaNode } from './templateSchemaPresentation';
import { formatTemplateSchemaType, normalizeTemplateSchema } from './templateSchemaPresentation';
import styles from './TemplateSchemaViewer.module.css';

interface TemplateSchemaViewerProps {
  schema: Record<string, unknown> | null | undefined;
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function FieldChoices({ node }: { node: TemplateSchemaNode }) {
  if (!node.enum?.length) return null;
  const visible = node.enum.slice(0, 6);
  const remaining = node.enum.slice(6);

  return (
    <div className={styles.fieldChoices}>
      <div className={styles.enumChips}>
        {visible.map((value, index) => <span className={styles.enumChip} key={`${formatValue(value)}-${index}`}>{formatValue(value)}</span>)}
      </div>
      {remaining.length > 0 && (
        <details className={styles.moreOptions}>
          <summary>Ещё {remaining.length}</summary>
          <div className={styles.enumChips}>
            {remaining.map((value, index) => <span className={styles.enumChip} key={`${formatValue(value)}-${index + 6}`}>{formatValue(value)}</span>)}
          </div>
        </details>
      )}
    </div>
  );
}

function FieldExtraDetails({ node }: { node: TemplateSchemaNode }) {
  const hasExample = node.example !== undefined && node.example !== null;
  if (!hasExample && !node.format) return null;

  return (
    <details className={styles.extraDetails}>
      <summary>Пример и формат</summary>
      <div className={styles.extraContent}>
        {node.format && <span><strong>Формат:</strong> {node.format}</span>}
        {hasExample && <span><strong>Пример:</strong> {formatValue(node.example)}</span>}
      </div>
    </details>
  );
}

function getTypeLabel(node: TemplateSchemaNode): string {
  if (node.kind === 'object') return 'Группа';
  if (node.kind === 'table') return 'Таблица';
  return formatTemplateSchemaType(node.type);
}

function RequiredMarker({ required }: { required: boolean }) {
  return required
    ? <span className={styles.requiredMark} title="Обязательное поле" aria-label="Обязательное поле">*</span>
    : null;
}

function FieldInfo({ node }: { node: TemplateSchemaNode }) {
  const description = node.description?.trim();
  return (
    <span className={styles.summaryContent}>
      <span className={styles.label}>{node.label}</span>
      {description && <span className={styles.description}>{description}</span>}
    </span>
  );
}

function NodeAside({ node }: { node: TemplateSchemaNode }) {
  return (
    <div className={styles.summaryAside}>
      {node.kind === 'scalar' && <FieldChoices node={node} />}
      <span className={styles.type}>{getTypeLabel(node)}</span>
      {node.required && <RequiredMarker required />}
    </div>
  );
}

function SchemaNode({ node, depth = 0 }: { node: TemplateSchemaNode; depth?: number }): ReactNode {
  const isScalar = node.kind === 'scalar';
  const isRoot = depth === 0;
  const className = node.kind === 'table'
    ? `${styles.node} ${isRoot ? styles.rootTableNode : styles.nestedTableNode}`
    : node.kind === 'object'
      ? `${styles.node} ${isRoot ? styles.rootObjectNode : styles.nestedObjectNode}`
      : `${styles.node} ${styles.fieldNode}`;

  if (isScalar) {
    return (
      <div className={className} key={node.path}>
        <div className={`${styles.nodeSummary} ${styles.fieldSummary}`}>
          <span className={styles.gutter} aria-hidden="true" />
          <FieldInfo node={node} />
          <NodeAside node={node} />
        </div>
        <FieldExtraDetails node={node} />
      </div>
    );
  }

  const description = node.description?.trim();
  const defaultOpen = depth === 0;
  return (
    <details className={className} key={node.path} open={defaultOpen}>
      <summary className={styles.nodeSummary}>
        <span className={styles.chevron} aria-hidden="true" />
        <span className={styles.summaryContent}>
          <span className={styles.label}>{node.label}</span>
          {description && <span className={styles.description}>{description}</span>}
        </span>
        <NodeAside node={node} />
      </summary>
      <div className={styles.nodeBody}>
        {node.fields.length > 0
          ? <div className={styles.children}>{node.fields.map((field) => <SchemaNode key={field.path} node={field} depth={depth + 1} />)}</div>
          : <p className={styles.emptyInline}>{node.kind === 'table' ? 'Столбцы не определены.' : 'В группе пока нет полей.'}</p>}
      </div>
    </details>
  );
}

export function TemplateSchemaViewer({ schema }: TemplateSchemaViewerProps) {
  const fields = normalizeTemplateSchema(schema);
  if (!schema) return <p className={styles.empty}>Схема ещё не сформирована.</p>;
  if (fields.length === 0) return <p className={styles.empty}>В схеме пока нет полей.</p>;

  return (
    <div className={styles.viewer}>
      <p className={styles.legend}><span aria-hidden="true">*</span> Обязательное поле</p>
      <div className={styles.tree}>
        {fields.map((field) => <SchemaNode key={field.path} node={field} />)}
      </div>
    </div>
  );
}

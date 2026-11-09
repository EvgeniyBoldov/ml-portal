import type { ReactNode } from 'react';
import { InspectorNotice } from '@/shared/ui/Inspector';
import styles from './InspectorPrimitives.module.css';

export function InspectorStack({ children }: { children: ReactNode }) {
  return <div className={styles.stack}>{children}</div>;
}

export function InspectorSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className={styles.section}><h4>{title}</h4>{children}</section>;
}

export function InspectorTable({ headers, children, compact = false, columnWidths }: {
  headers: string[];
  children: ReactNode;
  compact?: boolean;
  columnWidths?: string[];
}) {
  return <div className={`${styles.tableWrap} ${compact ? styles.tableWrapCompact : ''}`}><table className={`${styles.table} ${compact ? styles.tableCompact : ''}`}>
    {columnWidths ? <colgroup>{columnWidths.map((width, index) => <col key={`${index}:${width}`} style={{ width }} />)}</colgroup> : null}
    <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
    <tbody>{children}</tbody>
  </table></div>;
}

export function InspectorEmptyState({ message }: { message: string }) {
  return <InspectorNotice tone="neutral" message={message} />;
}

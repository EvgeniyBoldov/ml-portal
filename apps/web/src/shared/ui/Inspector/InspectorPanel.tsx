import type { ReactNode } from 'react';
import styles from './Inspector.module.css';

interface InspectorPanelProps {
  header: ReactNode;
  children: ReactNode;
}

export function InspectorPanel({ header, children }: InspectorPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.header}>{header}</div>
      <div className={styles.body}>{children}</div>
    </div>
  );
}

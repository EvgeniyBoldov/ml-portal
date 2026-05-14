import type { ReactNode } from 'react';
import styles from '../Inspector.module.css';

export function InspectorFieldGroup({ children }: { children: ReactNode }) {
  return <div className={styles.fields}>{children}</div>;
}

export function InspectorFieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{children}</span>
    </div>
  );
}

export function InspectorJsonBlock({ value }: { value: unknown }) {
  return <pre className={styles.code}>{JSON.stringify(value, null, 2)}</pre>;
}

export function InspectorTextBlock({ text }: { text: string }) {
  return <pre className={styles.code}>{text}</pre>;
}

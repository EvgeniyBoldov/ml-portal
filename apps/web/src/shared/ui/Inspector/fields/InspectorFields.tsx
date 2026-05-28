import { useState } from 'react';
import type { ReactNode } from 'react';
import { SmartViewer } from '@/shared/ui/SmartViewer';
import { SmartViewerModal } from '@/shared/ui/SmartViewer';
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
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.code}>
      <div className={styles.jsonActions}>
        <button type="button" className={styles.jsonExpandBtn} onClick={() => setOpen(true)} title="Открыть просмотр">
          ↗
        </button>
      </div>
      <SmartViewer value={value} />
      <SmartViewerModal value={value} open={open} onClose={() => setOpen(false)} title="JSON Viewer" />
    </div>
  );
}

export function InspectorTextBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.code}>
      <div className={styles.jsonActions}>
        <button type="button" className={styles.jsonExpandBtn} onClick={() => setOpen(true)} title="Открыть просмотр">
          ↗
        </button>
      </div>
      <SmartViewer value={text} />
      <SmartViewerModal value={text} open={open} onClose={() => setOpen(false)} title="Viewer" />
    </div>
  );
}

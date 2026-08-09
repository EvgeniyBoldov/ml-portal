import { useState } from 'react';
import type { ReactNode } from 'react';
import Badge from '@/shared/ui/Badge';
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
      <div className={styles.value}>{children}</div>
    </div>
  );
}

export function InspectorScalar({ value }: { value: string | number | boolean | null | undefined }) {
  const text = value === null || value === undefined || value === ''
    ? '—'
    : typeof value === 'boolean'
      ? value ? 'Да' : 'Нет'
      : String(value);
  return <span className={styles.scalar}>{text}</span>;
}

export function InspectorStatus({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
}) {
  return <Badge size="small" tone={tone}>{label}</Badge>;
}

export function InspectorDate({ value }: { value: string | null | undefined }) {
  if (!value) return <InspectorScalar value={undefined} />;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <InspectorScalar value={value} />;
  return <InspectorScalar value={date.toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'medium' })} />;
}

export function InspectorReadonlyBlock({ value }: { value: unknown }) {
  const text = typeof value === 'string' ? value : (() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  })();
  return <textarea className={styles.readonlyCode} value={text} readOnly spellCheck={false} aria-label="Только для чтения" />;
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

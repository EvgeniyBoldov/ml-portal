import Badge from '@/shared/ui/Badge';
import styles from './Inspector.module.css';

interface InspectorHeaderProps {
  tone: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
  kindLabel: string;
  title: string;
  meta?: string;
}

export function InspectorHeader({ tone, kindLabel, title, meta }: InspectorHeaderProps) {
  return (
    <>
      <Badge tone={tone} size="medium">{kindLabel}</Badge>
      <span className={styles.headerTitle} title={title}>{title}</span>
      {meta ? <span className={styles.headerMeta}>{meta}</span> : null}
    </>
  );
}

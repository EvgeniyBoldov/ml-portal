import { useState, type ReactNode } from 'react';
import styles from './SessionSidebar.module.css';

interface Props {
  title: string;
  count?: number;
  defaultExpanded?: boolean;
  children: ReactNode;
  actions?: ReactNode;
}

export default function AccordionSection({
  title,
  count,
  defaultExpanded = false,
  children,
  actions,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <section className={styles.section}>
      <div className={styles['section-header-row']}>
        <button
          type="button"
          className={styles['section-header']}
          aria-expanded={expanded}
          onClick={() => setExpanded((prev: boolean) => !prev)}
        >
          <span className={styles['section-title']}>
            {title}
            {count !== undefined ? ` (${count})` : ''}
          </span>
          <span className={`${styles['section-toggle']} ${expanded ? styles.expanded : ''}`}>
            ▾
          </span>
        </button>
        {actions ? <div className={styles['section-actions']}>{actions}</div> : null}
      </div>
      {expanded ? <div className={styles['section-content']}>{children}</div> : null}
    </section>
  );
}

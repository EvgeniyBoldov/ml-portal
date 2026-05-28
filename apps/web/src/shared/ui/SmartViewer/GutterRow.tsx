import type { ReactNode } from 'react';
import styles from './SmartViewer.module.css';

interface GutterRowProps {
  depth: number;
  foldable: boolean;
  folded: boolean;
  onToggle?: () => void;
  children: ReactNode;
  isClosing?: boolean;
}

export function GutterRow({ depth, foldable, folded, onToggle, children, isClosing = false }: GutterRowProps) {
  const indent = isClosing ? (depth - 1) * 14 : depth * 14;

  return (
    <div className={styles.row}>
      <div className={styles.gutter}>
        {foldable ? (
          <button
            type="button"
            className={styles.gutterMarker}
            onClick={onToggle}
            aria-label={folded ? 'Expand' : 'Collapse'}
          >
            {folded ? '▸' : '▾'}
          </button>
        ) : (
          <span className={styles.gutterSpacer} />
        )}
      </div>
      <div className={styles.rowContent} style={{ paddingLeft: indent }}>
        {children}
      </div>
    </div>
  );
}

import { useMemo, useState } from 'react';
import { Modal } from '@/shared/ui';
import { parseValue } from './useSmartParse';
import { SmartViewer } from './SmartViewer';
import styles from './SmartViewer.module.css';

interface SmartViewerModalProps {
  value: unknown;
  open: boolean;
  onClose: () => void;
  title?: string;
  mode?: 'view' | 'edit';
  onChange?: (raw: string) => void;
}

function tryStringifyPretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function SmartViewerModal({
  value,
  open,
  onClose,
  title = 'Viewer',
  mode = 'view',
  onChange,
}: SmartViewerModalProps) {
  const [copied, setCopied] = useState(false);
  const rawString = useMemo(() => tryStringifyPretty(value), [value]);

  const editParsed = useMemo(() => {
    if (mode !== 'edit') return null;
    if (typeof value === 'string') return parseValue(value, 0);
    return parseValue(value, 0);
  }, [value, mode]);

  const handleCopy = () => {
    void navigator.clipboard.writeText(rawString).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <Modal open={open} title={title} onClose={onClose} size="xl" bodyClassName={styles.modalBody}>
      <div className={styles.modalHeader}>
        <button type="button" className={styles.copyBtn} onClick={handleCopy}>
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>

      {mode === 'view' && (
        <div className={styles.modalScrollArea}>
          <SmartViewer value={value} />
        </div>
      )}

      {mode === 'edit' && (
        <div className={styles.modalEditSplit}>
          <div className={styles.modalEditPane}>
            <div className={styles.modalEditLabel}>Raw</div>
            <textarea
              className={styles.modalEditTextarea}
              value={rawString}
              onChange={(e) => onChange?.(e.target.value)}
              spellCheck={false}
            />
          </div>
          <div className={styles.modalPreviewPane}>
            <div className={styles.modalPreviewLabel}>Preview</div>
            {editParsed && (
              <div className={styles.root}>
                <SmartViewer value={value} />
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { Modal } from '@/shared/ui';
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
  const [draft, setDraft] = useState(rawString);

  useEffect(() => {
    if (mode === 'edit') {
      setDraft(rawString);
    }
  }, [mode, rawString, open]);

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
              value={draft}
              onChange={(e) => {
                const next = e.target.value;
                setDraft(next);
                onChange?.(next);
              }}
              spellCheck={false}
            />
          </div>
          <div className={styles.modalPreviewPane}>
            <div className={styles.modalPreviewLabel}>Preview</div>
            <div className={styles.root}>
              <SmartViewer value={draft} />
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

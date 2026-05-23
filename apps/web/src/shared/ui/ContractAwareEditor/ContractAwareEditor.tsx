import { useEffect, useMemo, useState } from 'react';

import type { ResponseContract } from '@/shared/api/admin';
import { Button, Modal, Textarea } from '@/shared/ui';
import { ContractLegend } from './ContractLegend';
import { useLiveCoverage } from './useLiveCoverage';
import styles from './ContractAwareEditor.module.css';

type Props = {
  value: string;
  onChange: (value: string) => void;
  outputContract?: ResponseContract | null;
  inputContract?: Record<string, unknown> | null;
  fieldLabel?: string;
  disabled?: boolean;
  rows?: number;
  placeholder?: string;
};

export function ContractAwareEditor({
  value,
  onChange,
  outputContract = null,
  inputContract = null,
  fieldLabel = 'Редактор',
  disabled = false,
  rows = 8,
  placeholder,
}: Props) {
  const [open, setOpen] = useState(false);

  const coverage = useLiveCoverage(value, outputContract ?? null);
  const hasLegend = Boolean(outputContract || inputContract);

  const bodyClassName = useMemo(() => {
    return hasLegend ? styles.modalBodySplit : styles.modalBodyPlain;
  }, [hasLegend]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  const appendLegendToken = (token: string) => {
    const trimmed = token.trim();
    if (!trimmed) return;
    const next = value.trim().length > 0 ? `${value}\n${trimmed}` : trimmed;
    onChange(next);
  };

  return (
    <>
      <div className={styles.inlineEditorShell}>
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          placeholder={placeholder}
          disabled={disabled}
          className={styles.inlineTextarea}
        />
        {!disabled && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={styles.expandButton}
            onClick={() => setOpen(true)}
            title="Открыть расширенный редактор"
          >
            ↗
          </Button>
        )}
      </div>

      <Modal
        open={open}
        title={fieldLabel}
        onClose={() => setOpen(false)}
        size="xl"
        className={styles.modal}
        bodyClassName={bodyClassName}
      >
        <div className={hasLegend ? styles.modalSplit : styles.modalSingle}>
          <div className={styles.editorPane}>
            <div className={styles.editorHeader}>
              <div className={styles.editorTitle}>{fieldLabel}</div>
              <div className={styles.editorHint}>
                Изменения применяются сразу в форме
              </div>
            </div>
            <Textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              rows={rows}
              placeholder={placeholder}
              disabled={disabled}
              className={styles.modalTextarea}
            />
          </div>

          {hasLegend && (
            <aside className={styles.legendPane}>
              <ContractLegend
                outputContract={outputContract}
                inputContract={inputContract}
                coverageMap={coverage.coverageMap}
                coveredCount={coverage.coveredCount}
                totalRequired={coverage.totalRequired}
                uncoveredFields={coverage.uncoveredFields}
                onFieldClick={appendLegendToken}
              />
            </aside>
          )}
        </div>
      </Modal>
    </>
  );
}

export default ContractAwareEditor;

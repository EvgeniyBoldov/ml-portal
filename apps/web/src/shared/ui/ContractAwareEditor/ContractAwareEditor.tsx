import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ResponseContract } from '@/shared/api/admin';
import { Button, Modal, Textarea } from '@/shared/ui';
import { ContractLegend } from './ContractLegend';
import { TextareaWithHighlight } from './highlight/TextareaWithHighlight';
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
  const [hoveredField, setHoveredField] = useState<string | null>(null);
  const [activeField, setActiveField] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const coverage = useLiveCoverage(value, outputContract ?? null);
  const hasLegend = Boolean(outputContract || inputContract);
  const knownFieldNames = useMemo(() => {
    const names = new Set<string>();
    for (const path of coverage.coverageMap.keys()) {
      const leaf = path.split('.').pop() ?? path;
      names.add(leaf.replace(/\[\]/g, ''));
    }
    return [...names];
  }, [coverage.coverageMap]);

  const bodyClassName = useMemo(() => {
    return hasLegend ? styles.modalBodySplit : styles.modalBodyPlain;
  }, [hasLegend]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  // R5: insert token at cursor position in modal textarea
  const insertAtCursor = useCallback(
    (token: string) => {
      const el = textareaRef.current;
      if (!el) {
        onChange(value ? `${value}\n${token}` : token);
        return;
      }
      const start = el.selectionStart ?? value.length;
      const end = el.selectionEnd ?? value.length;
      const next = value.slice(0, start) + token + value.slice(end);
      onChange(next);
      requestAnimationFrame(() => {
        el.selectionStart = el.selectionEnd = start + token.length;
        el.focus();
      });
    },
    [value, onChange],
  );

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
            <TextareaWithHighlight
              value={value}
              onChange={onChange}
              hoveredField={hoveredField}
              activeField={activeField}
              placeholder={placeholder}
              disabled={disabled}
              textareaRef={textareaRef}
              knownFields={knownFieldNames}
              onMarkClick={(field) => {
                setActiveField(field);
                setHoveredField(field);
              }}
              onTextFieldSelect={(field) => {
                if (!field) return;
                setActiveField(field);
                setHoveredField(field);
              }}
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
                onInsert={insertAtCursor}
                onHoverField={setHoveredField}
                activeField={activeField}
              />
            </aside>
          )}
        </div>
      </Modal>
    </>
  );
}

export default ContractAwareEditor;

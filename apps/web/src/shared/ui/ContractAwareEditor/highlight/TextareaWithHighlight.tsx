import { useEffect, useMemo, useRef } from 'react';
import type { RefObject } from 'react';

import { buildHighlightedHtml, findFieldMentions } from './tokenize';
import styles from '../ContractAwareEditor.module.css';

type Props = {
  value: string;
  hoveredField: string | null;
  activeField?: string | null;
  knownFields?: string[];
  placeholder?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  textareaRef?: RefObject<HTMLTextAreaElement>;
  onMarkClick?: (fieldName: string) => void;
  onTextFieldSelect?: (fieldName: string | null) => void;
};

export function TextareaWithHighlight({
  value,
  hoveredField,
  activeField,
  knownFields = [],
  placeholder,
  disabled = false,
  onChange,
  textareaRef,
  onMarkClick,
  onTextFieldSelect,
}: Props) {
  const localRef = useRef<HTMLTextAreaElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const ref = textareaRef ?? localRef;

  const ranges = useMemo(() => {
    if (!hoveredField) return [];
    return findFieldMentions(value, hoveredField);
  }, [value, hoveredField]);

  const html = useMemo(
    () => buildHighlightedHtml(value, ranges, hoveredField ?? activeField ?? null),
    [value, ranges, hoveredField, activeField],
  );

  const detectFieldAtCaret = () => {
    if (!onTextFieldSelect) return;
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    if (start !== end) return;

    const text = value ?? '';
    if (!text) return;
    const left = text.slice(0, start);
    const right = text.slice(start);
    const leftMatch = left.match(/[A-Za-z0-9_{}]+$/);
    const rightMatch = right.match(/^[A-Za-z0-9_{}]+/);
    const raw = `${leftMatch?.[0] ?? ''}${rightMatch?.[0] ?? ''}`.trim();
    if (!raw) {
      onTextFieldSelect(null);
      return;
    }
    const normalized = raw.replace(/[{}[\].,;:()"'`]/g, '').toLowerCase();
    if (!normalized) {
      onTextFieldSelect(null);
      return;
    }
    const match = knownFields.find((field) => field.toLowerCase() === normalized) ?? null;
    onTextFieldSelect(match);
  };

  useEffect(() => {
    const textarea = ref.current;
    const overlay = overlayRef.current;
    if (!textarea || !overlay) return;

    const sync = () => {
      overlay.scrollTop = textarea.scrollTop;
      overlay.scrollLeft = textarea.scrollLeft;
    };
    sync();
    textarea.addEventListener('scroll', sync);
    return () => textarea.removeEventListener('scroll', sync);
  }, [ref, value]);

  return (
    <div className={styles.highlightEditorWrap}>
      <div
        className={styles.highlightOverlay}
        ref={overlayRef}
        aria-hidden="true"
        style={{ pointerEvents: hoveredField || activeField ? 'auto' : 'none' }}
        onClick={(event) => {
          const target = event.target as HTMLElement | null;
          if (!target) return;
          const mark = target.closest('mark[data-field]');
          if (!(mark instanceof HTMLElement)) return;
          const field = mark.dataset.field;
          if (field) onMarkClick?.(field);
        }}
      >
        <pre
          className={styles.highlightOverlayPre}
          dangerouslySetInnerHTML={{ __html: `${html || '&nbsp;'}\n` }}
        />
      </div>
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onClick={detectFieldAtCaret}
        onKeyUp={detectFieldAtCaret}
        onMouseUp={() => {
          const el = ref.current;
          if (!el || !onTextFieldSelect) return;
          const start = el.selectionStart ?? 0;
          const end = el.selectionEnd ?? 0;
          if (start === end) return;
          const raw = value.slice(start, end).trim();
          if (!raw) return;
          const normalized = raw.replace(/[{}[\].,;:()"'`]/g, '').toLowerCase();
          if (!normalized) return;
          const match = knownFields.find((field) => field.toLowerCase() === normalized) ?? null;
          if (match) onTextFieldSelect(match);
        }}
        placeholder={placeholder}
        disabled={disabled}
        className={styles.modalTextareaHighlight}
      />
    </div>
  );
}

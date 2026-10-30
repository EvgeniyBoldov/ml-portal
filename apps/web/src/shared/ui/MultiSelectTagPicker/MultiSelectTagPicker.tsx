import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Input from '@/shared/ui/Input';
import styles from './MultiSelectTagPicker.module.css';

export type MultiSelectTagOption = { value: string; label: string; secondary?: string; search?: string };
export type MultiSelectTagPickerProps = {
  label: string;
  options: MultiSelectTagOption[];
  value: string[];
  lockedValues?: string[];
  disabled?: boolean;
  readOnly?: boolean;
  hideLabel?: boolean;
  placeholder?: string;
  emptyMessage?: string;
  unavailableLabel?: string;
  onChange: (values: string[]) => void;
};

export default function MultiSelectTagPicker({
  label,
  options,
  value,
  lockedValues = [],
  disabled,
  readOnly = false,
  hideLabel = false,
  placeholder,
  emptyMessage = 'Нет выбранных элементов',
  unavailableLabel = 'Недоступная запись',
  onChange,
}: MultiSelectTagPickerProps) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>();
  const controlRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef<HTMLDivElement>(null);
  const needle = query.trim().toLocaleLowerCase();
  const available = options.filter((option) => !value.includes(option.value) &&
    (!needle || `${option.label} ${option.secondary ?? ''} ${option.search ?? ''}`.toLocaleLowerCase().includes(needle)));
  const select = (option: MultiSelectTagOption) => {
    if (disabled || readOnly) return;
    onChange([...value, option.value]);
    setQuery('');
    setActiveIndex(0);
    setOpen(true);
  };
  useEffect(() => {
    if (readOnly || disabled) {
      setOpen(false);
      setDropdownStyle(undefined);
      return;
    }
    if (!open) {
      setDropdownStyle(undefined);
      return;
    }
    const updatePosition = () => {
      const rect = controlRef.current?.getBoundingClientRect();
      if (!rect) return;
      const dropdownHeight = Math.min(220, available.length * 40 + 8);
      const openUp = window.innerHeight - rect.bottom < dropdownHeight && rect.top > window.innerHeight - rect.bottom;
      setDropdownStyle({
        left: rect.left,
        top: openUp ? Math.max(4, rect.top - dropdownHeight - 4) : rect.bottom + 4,
        width: rect.width,
      });
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [available.length, disabled, open, readOnly]);
  useEffect(() => {
    if (open) {
      const activeOption = optionsRef.current?.children[activeIndex] as HTMLElement | undefined;
      activeOption?.scrollIntoView?.({ block: 'nearest' });
    }
  }, [activeIndex, open]);
  return <div className={styles.picker}>
    {!hideLabel && <label htmlFor={id}>{label}</label>}
    <div ref={controlRef} className={styles.control} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
    }}>
      <div
        className={styles.tags}
        role={readOnly && value.length > 0 ? 'list' : undefined}
        aria-label={readOnly && value.length > 0 ? label : undefined}
      >
        {readOnly && value.length === 0 && <span className={styles.emptyMessage} role="status">{emptyMessage}</span>}
        {value.map((key) => {
          const option = options.find((item) => item.value === key);
          const name = option?.label ?? unavailableLabel;
          return <span key={key} className={styles.tag} role={readOnly ? 'listitem' : undefined}>
            <span className={styles.tagContent}>
              <span className={styles.tagPrimary}>{name}</span>
              {option?.secondary && <span className={styles.tagSecondary}>{option.secondary}</span>}
            </span>
            {!readOnly && (lockedValues.includes(key)
              ? <span className={styles.lockedLabel}>Рабочая группа</span>
              : <button type="button" aria-label={`Убрать ${name}`} disabled={disabled} onClick={() => onChange(value.filter((item) => item !== key))}>×</button>)}
          </span>;
        })}
        {!readOnly && <Input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open && available.length > 0}
          aria-controls={`${id}-listbox`} aria-activedescendant={open && available[activeIndex] ? `${id}-option-${activeIndex}` : undefined}
          aria-label={label} value={query} disabled={disabled} placeholder={placeholder ?? (value.length ? 'Добавить…' : 'Выберите или начните вводить')}
          className={styles.searchInput} onFocus={() => { setOpen(true); setActiveIndex(0); }} onChange={(event) => {
            setQuery(event.target.value); setActiveIndex(0); setOpen(true);
          }} onKeyDown={(event) => {
            if (event.key === 'ArrowDown' && available.length) {
              event.preventDefault(); setOpen(true); setActiveIndex((index) => (index + 1) % available.length);
            } else if (event.key === 'ArrowUp' && available.length) {
              event.preventDefault(); setOpen(true); setActiveIndex((index) => (index - 1 + available.length) % available.length);
            } else if (event.key === 'Enter' && open && available[activeIndex]) {
              event.preventDefault(); select(available[activeIndex]);
            } else if (event.key === 'Escape') setOpen(false);
            else if (event.key === 'Backspace' && !query && value.length) onChange(value.slice(0, -1));
          }} />}
      </div>
      {!readOnly && !disabled && open && available.length > 0 && dropdownStyle && createPortal(<div id={`${id}-listbox`} ref={optionsRef} role="listbox" aria-label={`Варианты: ${label}`} className={styles.options} style={dropdownStyle}>
        {available.map((option, index) => <button id={`${id}-option-${index}`} key={option.value} type="button" role="option"
          aria-selected={index === activeIndex} className={index === activeIndex ? styles.optionActive : styles.option}
          onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setActiveIndex(index)} onClick={() => select(option)}>
          <span className={styles.optionLabel}>{option.label}</span>
          {option.secondary && <span className={styles.optionSecondary}>{option.secondary}</span>}
        </button>)}
      </div>, document.body)}
    </div>
  </div>;
}

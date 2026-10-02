import { useEffect, useId, useRef, useState } from 'react';
import { Input } from '@/shared/ui';
import styles from './MemoryTagPicker.module.css';

type Option = { value: string; label: string; search?: string };
type Props = { label: string; options: Option[]; value: string[]; disabled?: boolean; onChange: (values: string[]) => void };

export default function MemoryTagPicker({ label, options, value, disabled, onChange }: Props) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const optionsRef = useRef<HTMLDivElement>(null);
  const needle = query.trim().toLocaleLowerCase();
  const available = options.filter((option) => !value.includes(option.value) &&
    (!needle || `${option.label} ${option.search ?? ''}`.toLocaleLowerCase().includes(needle)));
  const select = (option: Option) => {
    onChange([...value, option.value]);
    setQuery('');
    setActiveIndex(0);
    setOpen(true);
  };
  useEffect(() => {
    if (open) optionsRef.current?.children[activeIndex]?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);
  return <div className={styles.picker}>
    <label htmlFor={id}>{label}</label>
    <div className={styles.control} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
    }}>
      <div className={styles.tags}>
        {value.map((key) => {
          const name = options.find((option) => option.value === key)?.label ?? 'Недоступная запись';
          return <span key={key} className={styles.tag}>{name}<button type="button" aria-label={`Убрать ${name}`} disabled={disabled} onClick={() => onChange(value.filter((item) => item !== key))}>×</button></span>;
        })}
        <Input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open && available.length > 0}
          aria-controls={`${id}-listbox`} aria-activedescendant={open && available[activeIndex] ? `${id}-option-${activeIndex}` : undefined}
          aria-label={label} value={query} disabled={disabled} placeholder={value.length ? 'Добавить…' : 'Выберите или начните вводить'}
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
          }} />
      </div>
      {open && available.length > 0 && <div id={`${id}-listbox`} ref={optionsRef} role="listbox" aria-label={`Варианты: ${label}`} className={styles.options}>
        {available.map((option, index) => <button id={`${id}-option-${index}`} key={option.value} type="button" role="option"
          aria-selected={index === activeIndex} className={index === activeIndex ? styles.optionActive : styles.option}
          onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setActiveIndex(index)} onClick={() => select(option)}>
          {option.label}
        </button>)}
      </div>}
    </div>
  </div>;
}

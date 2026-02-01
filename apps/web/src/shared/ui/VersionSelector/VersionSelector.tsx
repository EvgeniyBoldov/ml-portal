/**
 * VersionSelector - Dropdown for selecting entity version
 */
import React, { useState, useRef, useEffect } from 'react';
import styles from './VersionSelector.module.css';

export interface VersionOption {
  version: number;
  status: 'draft' | 'active' | 'inactive';
  label?: string;
}

export interface VersionSelectorProps {
  /** Available versions */
  versions: VersionOption[];
  /** Currently selected version */
  selectedVersion?: number;
  /** Change handler */
  onChange: (version: number) => void;
  /** Label above selector */
  label?: string;
  /** Additional class name */
  className?: string;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  active: 'Активная',
  inactive: 'Неактивная',
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'default',
  active: 'success',
  inactive: 'muted',
};

export function VersionSelector({
  versions,
  selectedVersion,
  onChange,
  label = 'Версия',
  className,
}: VersionSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const selected = versions.find((v) => v.version === selectedVersion);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (version: number) => {
    onChange(version);
    setIsOpen(false);
  };

  return (
    <div className={`${styles.wrap} ${className || ''}`} ref={ref}>
      {label && <span className={styles.label}>{label}</span>}
      
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className={styles.triggerText}>
          {selected ? (
            <>
              v{selected.version}
              <span className={`${styles.badge} ${styles[STATUS_COLORS[selected.status]]}`}>
                {STATUS_LABELS[selected.status]}
              </span>
            </>
          ) : (
            'Выберите версию'
          )}
        </span>
        <svg className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {isOpen && (
        <div className={styles.dropdown}>
          {versions.map((v) => (
            <button
              key={v.version}
              type="button"
              className={`${styles.option} ${v.version === selectedVersion ? styles.optionSelected : ''}`}
              onClick={() => handleSelect(v.version)}
            >
              <span>v{v.version}</span>
              <span className={`${styles.badge} ${styles[STATUS_COLORS[v.status]]}`}>
                {STATUS_LABELS[v.status]}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default VersionSelector;

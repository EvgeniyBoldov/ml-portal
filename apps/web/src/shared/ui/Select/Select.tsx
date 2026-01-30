/**
 * Select - Кастомный выпадающий список
 * 
 * Стилизованный под тему проекта, с поддержкой:
 * - Keyboard navigation (arrows, Enter, Escape)
 * - Placeholder
 * - Disabled state
 * - Error state
 * - Portal rendering для z-index
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './Select.module.css';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps {
  options: SelectOption[];
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  error?: boolean;
  className?: string;
  id?: string;
  name?: string;
}

export function Select({
  options,
  value,
  onChange,
  placeholder = 'Выберите...',
  disabled = false,
  error = false,
  className,
  id,
  name,
}: SelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0, width: 0 });

  const selectedOption = options.find(opt => opt.value === value);

  // Calculate menu position
  const updatePosition = useCallback(() => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
      });
    }
  }, []);

  // Open/close handlers
  const openMenu = useCallback(() => {
    if (disabled) return;
    updatePosition();
    setIsOpen(true);
    const selectedIdx = options.findIndex(opt => opt.value === value);
    setFocusedIndex(selectedIdx >= 0 ? selectedIdx : 0);
  }, [disabled, updatePosition, options, value]);

  const closeMenu = useCallback(() => {
    setIsOpen(false);
    setFocusedIndex(-1);
    triggerRef.current?.focus();
  }, []);

  const selectOption = useCallback((option: SelectOption) => {
    if (option.disabled) return;
    onChange?.(option.value);
    closeMenu();
  }, [onChange, closeMenu]);

  // Keyboard navigation
  const handleTriggerKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (disabled) return;
    
    switch (e.key) {
      case 'Enter':
      case ' ':
      case 'ArrowDown':
        e.preventDefault();
        openMenu();
        break;
      case 'ArrowUp':
        e.preventDefault();
        openMenu();
        break;
    }
  }, [disabled, openMenu]);

  const handleMenuKeyDown = useCallback((e: React.KeyboardEvent) => {
    const enabledOptions = options.filter(opt => !opt.disabled);
    const enabledCount = enabledOptions.length;

    switch (e.key) {
      case 'Escape':
        e.preventDefault();
        closeMenu();
        break;

      case 'ArrowDown':
        e.preventDefault();
        setFocusedIndex(prev => {
          let next = prev + 1;
          while (next < options.length && options[next]?.disabled) next++;
          return next < options.length ? next : prev;
        });
        break;

      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex(prev => {
          let next = prev - 1;
          while (next >= 0 && options[next]?.disabled) next--;
          return next >= 0 ? next : prev;
        });
        break;

      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusedIndex >= 0 && options[focusedIndex] && !options[focusedIndex].disabled) {
          selectOption(options[focusedIndex]);
        }
        break;

      case 'Tab':
        closeMenu();
        break;
    }
  }, [options, focusedIndex, closeMenu, selectOption]);

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        menuRef.current && !menuRef.current.contains(e.target as Node) &&
        triggerRef.current && !triggerRef.current.contains(e.target as Node)
      ) {
        closeMenu();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, closeMenu]);

  // Scroll focused item into view
  useEffect(() => {
    if (isOpen && focusedIndex >= 0 && menuRef.current) {
      const items = menuRef.current.querySelectorAll('[role="option"]');
      items[focusedIndex]?.scrollIntoView({ block: 'nearest' });
    }
  }, [isOpen, focusedIndex]);

  // Update position on scroll/resize
  useEffect(() => {
    if (!isOpen) return;

    const handleUpdate = () => updatePosition();
    window.addEventListener('scroll', handleUpdate, true);
    window.addEventListener('resize', handleUpdate);
    return () => {
      window.removeEventListener('scroll', handleUpdate, true);
      window.removeEventListener('resize', handleUpdate);
    };
  }, [isOpen, updatePosition]);

  const menu = isOpen && (
    <div
      ref={menuRef}
      role="listbox"
      className={styles.menu}
      style={{
        top: menuPosition.top,
        left: menuPosition.left,
        width: menuPosition.width,
      }}
      onKeyDown={handleMenuKeyDown}
    >
      {options.map((option, index) => (
        <div
          key={option.value}
          role="option"
          aria-selected={option.value === value}
          aria-disabled={option.disabled}
          className={`${styles.option} ${
            option.value === value ? styles.selected : ''
          } ${option.disabled ? styles.disabled : ''} ${
            index === focusedIndex ? styles.focused : ''
          }`}
          onClick={() => selectOption(option)}
          onMouseEnter={() => !option.disabled && setFocusedIndex(index)}
        >
          {option.value === value && (
            <svg className={styles.checkIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
          <span className={styles.optionLabel}>{option.label}</span>
        </div>
      ))}
    </div>
  );

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={id ? `${id}-listbox` : undefined}
        id={id}
        name={name}
        disabled={disabled}
        className={`${styles.trigger} ${error ? styles.error : ''} ${
          isOpen ? styles.open : ''
        } ${className || ''}`}
        onClick={() => isOpen ? closeMenu() : openMenu()}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className={selectedOption ? styles.value : styles.placeholder}>
          {selectedOption?.label || placeholder}
        </span>
        <svg 
          width="16" 
          height="16" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round"
          className={`${styles.arrow} ${isOpen ? styles.arrowOpen : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {createPortal(menu, document.body)}
    </>
  );
}

export default Select;

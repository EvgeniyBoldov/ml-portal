/**
 * SecretField - универсальное поле для секретных значений.
 *
 * Режимы:
 * - view: показывает ****** с кнопкой "показать" (reveal) и "установить новый"
 * - edit: показывает Input для ввода нового значения с кнопкой "установить"
 *
 * При reveal показывает зашифрованное значение (encrypted_payload).
 * При edit очищает поле и позволяет ввести новое значение.
 */
import React, { useState, useCallback } from 'react';
import { Icon } from '../Icon';
import Input from '../Input';
import Button from '../Button';
import styles from './SecretField.module.css';

export interface SecretFieldProps {
  /** Зашифрованное значение для отображения при reveal */
  encryptedValue?: string;
  /** Callback при установке нового значения */
  onSave?: (value: string) => void;
  /** Блокировка */
  disabled?: boolean;
  /** Placeholder для поля ввода */
  placeholder?: string;
  /** Подсказка под полем */
  hint?: string;
  /** Сохранение в процессе */
  saving?: boolean;
}

export function SecretField({
  encryptedValue,
  onSave,
  disabled = false,
  placeholder = 'Введите новое значение...',
  hint,
  saving = false,
}: SecretFieldProps) {
  const [mode, setMode] = useState<'masked' | 'revealed' | 'edit'>('masked');
  const [newValue, setNewValue] = useState('');

  const handleReveal = useCallback(() => {
    setMode((prev) => (prev === 'revealed' ? 'masked' : 'revealed'));
  }, []);

  const handleStartEdit = useCallback(() => {
    setMode('edit');
    setNewValue('');
  }, []);

  const handleCancel = useCallback(() => {
    setMode('masked');
    setNewValue('');
  }, []);

  const handleSave = useCallback(() => {
    if (!newValue.trim() || !onSave) return;
    onSave(newValue.trim());
    setMode('masked');
    setNewValue('');
  }, [newValue, onSave]);

  if (mode === 'edit') {
    return (
      <div className={styles.wrapper}>
        <div className={styles.editRow}>
          <Input
            className={styles.input}
            type="text"
            value={newValue}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewValue(e.target.value)}
            placeholder={placeholder}
            autoFocus
            disabled={disabled || saving}
            onKeyDown={(e: React.KeyboardEvent) => {
              if (e.key === 'Enter') handleSave();
              if (e.key === 'Escape') handleCancel();
            }}
          />
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!newValue.trim() || disabled || saving}
          >
            {saving ? 'Сохранение...' : 'Установить'}
          </Button>
          <button
            className={styles.iconBtn}
            onClick={handleCancel}
            title="Отмена"
            disabled={saving}
          >
            <Icon name="x" size={16} />
          </button>
        </div>
        {hint && <div className={styles.hint}>{hint}</div>}
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.fieldRow}>
        {mode === 'revealed' && encryptedValue ? (
          <div className={styles.revealedValue}>
            {encryptedValue}
          </div>
        ) : (
          <div className={styles.maskedValue}>
            <span className={styles.maskedDots}>••••••••••••</span>
          </div>
        )}
        <div className={styles.actions}>
          {encryptedValue && (
            <button
              className={styles.iconBtn}
              onClick={handleReveal}
              title={mode === 'revealed' ? 'Скрыть' : 'Показать зашифрованное'}
              disabled={disabled}
            >
              <Icon name={mode === 'revealed' ? 'eye-off' : 'eye'} size={16} />
            </button>
          )}
          {onSave && (
            <button
              className={styles.iconBtn}
              onClick={handleStartEdit}
              title="Установить новое значение"
              disabled={disabled}
            >
              <Icon name="edit-2" size={16} />
            </button>
          )}
        </div>
      </div>
      {hint && <div className={styles.hint}>{hint}</div>}
    </div>
  );
}

export default SecretField;

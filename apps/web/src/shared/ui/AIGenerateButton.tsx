/**
 * AIGenerateButton - Button for AI-powered content generation
 */
import React, { useState } from 'react';
import { Button } from '@/shared/ui';
import { useAIGenerate } from '@/shared/hooks/useAIGenerate';
import type { VersionGenerateRequest } from '@/shared/api/aiGenerate';
import styles from './AIGenerateButton.module.css';

interface AIGenerateButtonProps {
  entityType: 'agent';
  entityId: string;
  description: string;
  availableFields: Array<{ key: string; label: string; description?: string }>;
  onFieldsFilled: (fields: Record<string, any>) => void;
  context?: Record<string, any>;
  disabled?: boolean;
  variant?: 'primary' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

export function AIGenerateButton({
  entityType,
  entityId,
  description,
  availableFields,
  onFieldsFilled,
  context = {},
  disabled = false,
  variant = 'outline',
  size = 'md',
}: AIGenerateButtonProps) {
  const [showFieldSelector, setShowFieldSelector] = useState(false);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);

  const { generate, isGenerating } = useAIGenerate({
    entityType,
    entityId,
    onSuccess: (filledFields, suggestions) => {
      onFieldsFilled(filledFields);
      setShowFieldSelector(false);
      
      // Показать предложения в toast или модалке
      if (suggestions.length > 0) {
        console.log('AI Suggestions:', suggestions);
      }
    },
  });

  const handleGenerate = () => {
    if (selectedFields.length === 0) {
      // Если поля не выбраны, генерируем для всех доступных полей
      const allFields = availableFields.map(f => f.key);
      setSelectedFields(allFields);
      generateWithFields(allFields);
    } else {
      generateWithFields(selectedFields);
    }
  };

  const generateWithFields = (fields: string[]) => {
    const requestData: VersionGenerateRequest = {
      description,
      fields,
      context,
    };

    generate(requestData);
  };

  const toggleField = (fieldKey: string) => {
    setSelectedFields(prev => 
      prev.includes(fieldKey) 
        ? prev.filter(f => f !== fieldKey)
        : [...prev, fieldKey]
    );
  };

  const selectAllFields = () => {
    setSelectedFields(availableFields.map(f => f.key));
  };

  const clearSelection = () => {
    setSelectedFields([]);
  };

  if (showFieldSelector) {
    return (
      <div className={styles['ai-generate-modal']}>
        <div className={styles['ai-generate-modal-backdrop']} onClick={() => setShowFieldSelector(false)} />
        <div className={styles['ai-generate-modal-content']}>
          <div className={styles['ai-generate-modal-header']}>
            <h3>🤖 Выберите поля для заполнения</h3>
            <button 
              className={styles['ai-generate-modal-close']}
              onClick={() => setShowFieldSelector(false)}
            >
              ×
            </button>
          </div>
          
          <div className={styles['ai-generate-modal-body']}>
            <div className={styles['ai-generate-field-selector']}>
              <div className={styles['ai-generate-field-selector-header']}>
                <div className={styles['ai-generate-field-selector-controls']}>
                  <button 
                    type="button"
                    className={styles['ai-generate-select-all']}
                    onClick={selectAllFields}
                  >
                    Выбрать все
                  </button>
                  <button 
                    type="button"
                    className={styles['ai-generate-clear-selection']}
                    onClick={clearSelection}
                  >
                    Очистить
                  </button>
                </div>
                <div className={styles['ai-generate-selected-count']}>
                  Выбрано: {selectedFields.length} из {availableFields.length}
                </div>
              </div>
              
              <div className={styles['ai-generate-field-list']}>
                {availableFields.map(field => (
                  <label key={field.key} className={styles['ai-generate-field-item']}>
                    <input
                      type="checkbox"
                      checked={selectedFields.includes(field.key)}
                      onChange={() => toggleField(field.key)}
                    />
                    <div className={styles['ai-generate-field-info']}>
                      <div className={styles['ai-generate-field-name']}>{field.label}</div>
                      {field.description && (
                        <div className={styles['ai-generate-field-description']}>
                          {field.description}
                        </div>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>
          
          <div className={styles['ai-generate-modal-footer']}>
            <button 
              className={styles['ai-generate-cancel']}
              onClick={() => setShowFieldSelector(false)}
            >
              Отмена
            </button>
            <Button
              variant="primary"
              onClick={handleGenerate}
              disabled={selectedFields.length === 0 || isGenerating}
              loading={isGenerating}
            >
              {isGenerating ? 'Генерирую...' : 'Сгенерировать'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={() => setShowFieldSelector(true)}
      disabled={disabled || !description.trim()}
      loading={isGenerating}
    >
      🤖 Заполнить с ИИ
    </Button>
  );
}

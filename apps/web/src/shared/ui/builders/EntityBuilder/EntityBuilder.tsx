/**
 * EntityBuilder - Universal component for building forms from entities
 * 
 * Использует ContentBlock поля напрямую, без дополнительной обертки
 */
import React from 'react';
import { ContentBlock, type FieldDefinition } from '../../ContentBlock';

export type EntityMode = 'view' | 'edit' | 'create';

export interface EntityBuilderProps<T> {
  /** Entity данные */
  entity: T;
  /** Определения полей формы */
  forms: FieldDefinition[];
  /** Режим отображения */
  mode: EntityMode;
  /** Обработчик изменений */
  onChange?: (key: string, value: any) => void;
  /** Дополнительные CSS классы */
  className?: string;
}

/**
 * EntityBuilder - универсальный компонент для отображения сущностей
 * 
 * @param entity - данные сущности
 * @param forms - массив определений полей
 * @param mode - режим отображения
 * @param onChange - обработчик изменений
 */
export function EntityBuilder<T>({
  entity,
  forms,
  mode,
  onChange,
  className,
}: EntityBuilderProps<T>) {
  // Подготовка данных для ContentBlock
  const data = React.useMemo(() => {
    if (!entity) return {}; // Защита от null
    
    const result: Record<string, any> = {};
    
    forms.forEach(field => {
      const value = entity[field.key as keyof T];
      
      // Преобразование значений для разных типов полей
      switch (field.type) {
        case 'date':
          result[field.key] = value ? new Date(value as string).toLocaleDateString('ru-RU') : '';
          break;
          
        case 'boolean':
          result[field.key] = Boolean(value);
          break;
          
        case 'number':
          result[field.key] = Number(value) || 0;
          break;
          
        case 'badge':
          // Для badge типа показываем текстовое представление
          if (field.key === 'current_version_status') {
            const statusLabels = { draft: 'Черновик', active: 'Активна', deprecated: 'Устарела' };
            result[field.key] = statusLabels[value as keyof typeof statusLabels] || value;
          } else if (field.key === 'current_version_number') {
            result[field.key] = value ? `v${value}` : '-';
          } else if (field.key === 'versions_count') {
            result[field.key] = String(value || 0);
          } else {
            result[field.key] = String(value || '-');
          }
          break;
          
        default:
          result[field.key] = value || '';
      }
    });
    
    return result;
  }, [entity, forms]);

  // Обработчик изменений
  const handleChange = React.useCallback((key: string, value: any) => {
    if (!onChange) return;
    
    // Обратное преобразование для разных типов полей
    let processedValue = value;
    
    const field = forms.find(f => f.key === key);
    if (!field) return;
    
    switch (field.type) {
      case 'date':
        // Для date типа ожидаем строку, конвертируем в ISO
        processedValue = value ? new Date(value).toISOString() : null;
        break;
        
      case 'boolean':
        processedValue = Boolean(value);
        break;
        
      case 'number':
        processedValue = Number(value) || 0;
        break;
        
      case 'badge':
          // Для badge типа преобразуем обратно в enum
          if (field.key === 'current_version_status') {
            const statusMap = { 'Черновик': 'draft', 'Активна': 'active', 'Устарела': 'deprecated' };
            processedValue = statusMap[value as keyof typeof statusMap] || value;
          } else if (field.key === 'current_version_number') {
            // Преобразуем "v3" обратно в 3
            processedValue = typeof value === 'string' && value.startsWith('v') 
              ? parseInt(value.slice(1), 10) 
              : value;
          }
          break;
        
      default:
        processedValue = value;
    }
    
    onChange(key, processedValue);
  }, [onChange, forms]);

  // Фильтрация полей для разных режимов
  const filteredForms = React.useMemo(() => {
    return forms.filter(field => {
      // В режиме view показываем все поля
      if (mode === 'view') return true;
      
      // В режимах edit/create скрываем поля с disabled=true
      if (field.disabled) return false;
      
      return true;
    });
  }, [forms, mode]);

  // Возвращаем только поля для ContentBlock, без обертки
  return React.useMemo(() => ({
    fields: filteredForms,
    data: data,
    editable: mode === 'edit' || mode === 'create',
    onChange: handleChange,
  }), [filteredForms, data, mode, handleChange]);
}

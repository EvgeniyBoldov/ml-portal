/**
 * RbacRuleBlock - Блок для отображения/редактирования RBAC правила (ресурс + эффект)
 * На основе ContentBlock из shared/ui
 */
import React from 'react';
import { ContentBlock, type FieldDefinition, type BlockWidth } from '../ContentBlock';
import { ResourceSelector } from './ResourceSelector';

// Интерфейсы для RBAC
export type ResourceType = 'agent' | 'tool' | 'instance';
export type RbacEffect = 'allow' | 'deny';

export interface RbacRuleData {
  resource_type: ResourceType;
  resource_id: string;
  effect: RbacEffect;
}

interface RbacRuleBlockProps {
  data: RbacRuleData;
  editable?: boolean;
  width?: BlockWidth;
  agents?: any[];
  onChange?: (key: keyof RbacRuleData, value: string) => void;
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  agent: 'Агент',
  tool: 'Инструмент',
  instance: 'Коннектор',
};

export function RbacRuleBlock({ 
  data, 
  editable = false, 
  width = '1/2',
  agents = [], 
  onChange 
}: RbacRuleBlockProps) {
  
  const getResourceName = (resourceId: string): string => {
    if (!resourceId) return RESOURCE_TYPE_LABELS[data.resource_type] || 'Не выбран';
    
    // Ищем в агентах
    const agent = agents.find((a: any) => a.id === resourceId);
    if (agent) return agent.name || agent.slug || resourceId;

    return RESOURCE_TYPE_LABELS[data.resource_type] || 'Ресурс';
  };

  const fields: FieldDefinition[] = [
    {
      key: 'resource_type',
      label: 'Тип ресурса',
      type: 'select',
      options: Object.entries(RESOURCE_TYPE_LABELS).map(([value, label]) => ({
        value,
        label
      })),
      disabled: !editable,
    },
    {
      key: 'resource_id',
      label: 'Ресурс',
      type: 'custom',
      disabled: !editable,
      render: (value: any, isEditable: boolean, onChange: (val: any) => void) => (
        <ResourceSelector
          resourceType={data.resource_type}
          value={value}
          onChange={onChange}
          agents={agents}
        />
      ),
    },
    {
      key: 'effect',
      label: 'Эффект',
      type: 'badge',
      badgeTone: data.effect === 'allow' ? 'success' : 'danger',
      disabled: !editable,
    },
  ];

  // Для edit mode показываем селект для эффекта
  if (editable) {
    fields[2] = {
      key: 'effect',
      label: 'Эффект',
      type: 'select',
      options: [
        { value: 'deny', label: 'Запрещён' },
        { value: 'allow', label: 'Разрешён' },
      ],
      disabled: !editable,
    };
  }

  return (
    <ContentBlock
      title="Правило доступа"
      icon="shield"
      iconVariant="info"
      width={width}
      editable={editable}
      fields={fields}
      data={{
        ...data,
        // Для badge типа показываем текстовое значение
        effect: editable ? data.effect : (data.effect === 'allow' ? 'Разрешён' : 'Запрещён'),
        // Для custom типа показываем красивое имя
        resource_id: editable ? data.resource_id : getResourceName(data.resource_id),
      }}
      onChange={(key, value) => onChange?.(key as keyof RbacRuleData, value)}
    />
  );
}

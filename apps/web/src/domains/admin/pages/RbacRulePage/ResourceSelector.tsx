/**
 * ResourceSelector - компонент для выбора ресурса в RBAC правиле
 */
import React from 'react';

interface ResourceSelectorProps {
  resourceType: string;
  value: any; // Теперь это объект ресурса, не string
  onChange: (resource: any) => void;
  agents: any[];
  toolGroups: any[];
}

export function ResourceSelector({ resourceType, value, onChange, agents, toolGroups }: ResourceSelectorProps) {
  const getResourceOptions = () => {
    switch (resourceType) {
      case 'agent':
        return agents.map(agent => ({
          value: agent,
          label: `${agent.name} (${agent.slug})`
        }));
      
      case 'toolgroup':
        return toolGroups.map(group => ({
          value: group,
          label: `${group.name} (${group.slug})`
        }));
      
      default:
        return [];
    }
  };

  const options = getResourceOptions();
  const selectedValue = value?.id || '';

  return (
    <select
      value={selectedValue}
      onChange={(e) => {
        const selected = options.find(opt => opt.value.id === e.target.value);
        onChange(selected?.value || null);
      }}
      disabled={!resourceType}
      style={{
        width: '100%',
        padding: '0.5rem',
        border: '1px solid var(--border-color)',
        borderRadius: '0.375rem',
        backgroundColor: 'var(--bg-primary)',
        color: 'var(--text-primary)'
      }}
    >
      <option value="">
        {!resourceType ? 'Сначала выберите тип ресурса' : 'Выберите ресурс'}
      </option>
      {options.map(option => (
        <option key={option.value.id} value={option.value.id}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/**
 * ResourceSelector - Компонент для выбора ресурса в RBAC правиле
 */
import React from 'react';
import styles from './ResourceSelector.module.css';

interface ResourceSelectorProps {
  resourceType: string;
  value: string;
  onChange: (resourceId: string) => void;
  agents: any[];
  toolGroups: any[];
}

export function ResourceSelector({ 
  resourceType, 
  value, 
  onChange, 
  agents, 
  toolGroups 
}: ResourceSelectorProps) {
  
  const getResourceOptions = () => {
    switch (resourceType) {
      case 'agent':
        return agents.map(agent => ({
          value: agent.id,
          label: `${agent.name} (${agent.slug})`
        }));
      
      case 'toolgroup':
        return toolGroups.map(group => ({
          value: group.id,
          label: `${group.name} (${group.slug})`
        }));
      
      default:
        return [];
    }
  };

  const options = getResourceOptions();

  return (
    <select
      className={styles.select}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={!resourceType}
    >
      <option value="">
        {!resourceType ? 'Сначала выберите тип ресурса' : 'Выберите ресурс'}
      </option>
      {options.map(option => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/**
 * FilterBar - Unified filter bar for list pages
 * 
 * Combines search input with filter dropdowns
 */
import React from 'react';
import Input from '../Input';
import Select from '../Select';
import { Icon } from '../Icon';
import styles from './FilterBar.module.css';

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterConfig {
  key: string;
  label: string;
  options: FilterOption[];
  value: string;
  onChange: (value: string) => void;
}

export interface FilterBarProps {
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  filters?: FilterConfig[];
  children?: React.ReactNode; // For custom filter elements
}

export function FilterBar({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Поиск...',
  filters,
  children,
}: FilterBarProps) {
  return (
    <div className={styles.bar}>
      {filters && filters.length > 0 && (
        <div className={styles.filters}>
          {filters.map(filter => (
            <div key={filter.key} className={styles.filterItem}>
              <span className={styles.filterLabel}>{filter.label}</span>
              <Select
                value={filter.value}
                onChange={(e) => filter.onChange(e.target.value)}
                options={filter.options}
                className={styles.filterSelect}
              />
            </div>
          ))}
        </div>
      )}
      
      {children && <div className={styles.custom}>{children}</div>}
      
      {onSearchChange && (
        <div className={styles.search}>
          <Icon name="search" size={16} className={styles.searchIcon} />
          <Input
            value={searchValue || ''}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className={styles.searchInput}
          />
        </div>
      )}
    </div>
  );
}

export default FilterBar;

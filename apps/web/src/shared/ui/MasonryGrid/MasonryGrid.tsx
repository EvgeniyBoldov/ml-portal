/**
 * MasonryGrid - Auto-adjusting grid layout system
 * 
 * Automatically adjusts block heights to fill space efficiently
 * Uses CSS Grid with auto-fit and minmax for responsive behavior
 */
import React from 'react';
import styles from './MasonryGrid.module.css';

export interface MasonryGridProps {
  children: React.ReactNode;
  /** Grid gap */
  gap?: 'sm' | 'md' | 'lg';
  /** Minimum column width */
  minColWidth?: number;
  /** Maximum number of columns */
  maxCols?: number;
  /** Additional CSS class */
  className?: string;
}

export function MasonryGrid({
  children,
  gap = 'md',
  minColWidth = 300,
  maxCols = 4,
  className = '',
}: MasonryGridProps) {
  return (
    <div 
      className={`${styles.masonryGrid} ${styles[gap]} ${className}`}
      style={{
        '--min-col-width': `${minColWidth}px`,
        '--max-cols': maxCols,
      } as React.CSSProperties}
    >
      {children}
    </div>
  );
}

export default MasonryGrid;

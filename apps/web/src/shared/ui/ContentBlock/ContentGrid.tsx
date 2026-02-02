/**
 * ContentGrid - Container for ContentBlock components
 * 
 * Uses CSS Grid with 12 columns for flexible layout
 * Blocks automatically fill available space without gaps
 */
import React from 'react';
import styles from './ContentGrid.module.css';

export interface ContentGridProps {
  /** Grid children (ContentBlock components) */
  children: React.ReactNode;
  /** Gap between blocks */
  gap?: 'sm' | 'md' | 'lg';
  /** Grid direction - row (horizontal) or column (vertical) */
  direction?: 'row' | 'column';
  /** Additional CSS class */
  className?: string;
}

export function ContentGrid({
  children,
  gap = 'md',
  direction = 'row',
  className = '',
}: ContentGridProps) {
  return (
    <div className={`${styles.grid} ${styles[`gap-${gap}`]} ${styles[`direction-${direction}`]} ${className}`}>
      {children}
    </div>
  );
}

export default ContentGrid;

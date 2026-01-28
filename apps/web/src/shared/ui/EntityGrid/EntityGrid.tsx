/**
 * EntityGrid - Flexible grid layout for entity page content
 * 
 * Supports various layouts:
 * - Single column (default)
 * - Two columns (2 blocks side by side)
 * - Two columns + full width row (2 blocks top, 1 full-width bottom)
 * 
 * Usage:
 * <EntityGrid>
 *   <EntityGrid.Column>Block 1</EntityGrid.Column>
 *   <EntityGrid.Column>Block 2</EntityGrid.Column>
 *   <EntityGrid.FullWidth>Block 3 (full width)</EntityGrid.FullWidth>
 * </EntityGrid>
 */
import React from 'react';
import styles from './EntityGrid.module.css';

interface EntityGridProps {
  children: React.ReactNode;
  /** Number of columns for the grid (1 or 2) */
  columns?: 1 | 2;
  /** Gap between grid items */
  gap?: 'sm' | 'md' | 'lg';
}

interface ColumnProps {
  children: React.ReactNode;
  /** Span full width regardless of grid columns */
  span?: 'full';
}

interface SectionProps {
  children: React.ReactNode;
  /** Section title */
  title?: string;
  /** Section icon */
  icon?: React.ReactNode;
  /** Collapsible section */
  collapsible?: boolean;
  /** Default collapsed state */
  defaultCollapsed?: boolean;
}

/**
 * Main grid container
 */
export function EntityGrid({ children, columns = 1, gap = 'md' }: EntityGridProps) {
  const className = [
    styles.grid,
    styles[`columns${columns}`],
    styles[`gap${gap}`],
  ].join(' ');

  return <div className={className}>{children}</div>;
}

/**
 * Grid column - can be half-width or full-width
 */
function Column({ children, span }: ColumnProps) {
  const className = span === 'full' ? styles.fullWidth : styles.column;
  return <div className={className}>{children}</div>;
}

/**
 * Full-width row
 */
function FullWidth({ children }: { children: React.ReactNode }) {
  return <div className={styles.fullWidth}>{children}</div>;
}

/**
 * Section block with optional title and icon
 */
function Section({ children, title, icon, collapsible, defaultCollapsed }: SectionProps) {
  const [collapsed, setCollapsed] = React.useState(defaultCollapsed ?? false);

  return (
    <div className={styles.section}>
      {title && (
        <div 
          className={`${styles.sectionHeader} ${collapsible ? styles.collapsible : ''}`}
          onClick={collapsible ? () => setCollapsed(!collapsed) : undefined}
        >
          {icon && <div className={styles.sectionIcon}>{icon}</div>}
          <h3 className={styles.sectionTitle}>{title}</h3>
          {collapsible && (
            <svg 
              className={`${styles.chevron} ${collapsed ? styles.collapsed : ''}`}
              width="16" 
              height="16" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          )}
        </div>
      )}
      {!collapsed && (
        <div className={styles.sectionContent}>
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Row within a section - for horizontal layout of fields
 */
function Row({ children }: { children: React.ReactNode }) {
  return <div className={styles.row}>{children}</div>;
}

// Attach sub-components
EntityGrid.Column = Column;
EntityGrid.FullWidth = FullWidth;
EntityGrid.Section = Section;
EntityGrid.Row = Row;

export default EntityGrid;

/**
 * JSONDisplay - Component for displaying JSON data with proper formatting
 * 
 * Features:
 * - Monospace font with syntax highlighting colors
 * - Scrollable for large JSON content
 * - Responsive and accessible
 */
import React from 'react';
import styles from './JSONDisplay.module.css';

export interface JSONDisplayProps {
  /** JSON string to display */
  value: string;
  /** Maximum height before scrolling */
  maxHeight?: string;
  /** Additional CSS class */
  className?: string;
}

export function JSONDisplay({ value, maxHeight = '400px', className = '' }: JSONDisplayProps) {
  return (
    <pre className={`${styles.jsonDisplay} ${className}`} style={{ maxHeight }}>
      <code>{value}</code>
    </pre>
  );
}

/**
 * JSONDisplaySimple - Simplified JSON display without header
 * 
 * Used inside Block components where header actions are handled by Block
 */
import React from 'react';
import styles from './JSONDisplay.module.css';

export interface JSONDisplaySimpleProps {
  /** JSON string to display */
  value: string;
  /** Maximum height before scrolling */
  maxHeight?: string;
  /** Additional CSS class */
  className?: string;
}

export function JSONDisplaySimple({ 
  value, 
  maxHeight = '400px', 
  className = '' 
}: JSONDisplaySimpleProps) {
  return (
    <div className={`${styles.jsonDisplaySimple} ${className}`} style={{ maxHeight }}>
      <pre className={styles.code}>
        <code>{value}</code>
      </pre>
    </div>
  );
}

export default JSONDisplaySimple;

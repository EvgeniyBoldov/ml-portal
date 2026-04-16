/**
 * JSONDisplay - Component for displaying JSON data with proper formatting
 * 
 * Features:
 * - Monospace font with syntax highlighting colors
 * - Scrollable for large JSON content
 * - Responsive and accessible
 * - Copy to clipboard functionality
 * - Expandable/collapsible
 */
import React, { useState } from 'react';
import { Button } from '@/shared/ui';
import styles from './JSONDisplay.module.css';

export interface JSONDisplayProps {
  /** JSON string to display */
  value: string;
  /** Maximum height before scrolling */
  maxHeight?: string;
  /** Additional CSS class */
  className?: string;
  /** Show copy button */
  showCopy?: boolean;
  /** Show expand/collapse button */
  showExpand?: boolean;
}

export function JSONDisplay({ 
  value, 
  maxHeight = '400px', 
  className = '', 
  showCopy = true,
  showExpand = false 
}: JSONDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(showExpand);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const toggleExpand = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className={`${styles.jsonDisplay} ${className}`} style={{ maxHeight: isExpanded ? 'none' : maxHeight }}>
      <div className={styles.header}>
        <div className={styles.headerInfo}>
          <span className={styles.headerTitle}>JSON</span>
          <span className={styles.headerSize}>
            {value.length.toLocaleString()} chars
          </span>
        </div>
        <div className={styles.headerActions}>
          {showCopy && (
            <Button
              onClick={handleCopy}
              variant="outline"
              size="small"
            >
              {copied ? 'Скопировано!' : 'Копировать'}
            </Button>
          )}
          {showExpand && (
            <Button
              onClick={toggleExpand}
              variant="outline"
              size="small"
            >
              {isExpanded ? 'Свернуть' : 'Развернуть'}
            </Button>
          )}
        </div>
      </div>
      <pre className={styles.code}>
        <code>{value}</code>
      </pre>
    </div>
  );
}

export default JSONDisplay;

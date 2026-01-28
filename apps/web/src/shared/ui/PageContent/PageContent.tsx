/**
 * PageContent - Container for page content with consistent padding
 */
import React from 'react';
import styles from './PageContent.module.css';

export interface PageContentProps {
  children: React.ReactNode;
  className?: string;
}

export function PageContent({ children, className }: PageContentProps) {
  return (
    <div className={`${styles.content} ${className || ''}`}>
      {children}
    </div>
  );
}

export default PageContent;

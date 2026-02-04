/**
 * BaseLayout - Unified layout system for admin pages
 * 
 * Types:
 * - "split" - Two column layout (container info | version/status)
 * - "tabs" - Tabbed layout (overview | versions | settings)
 * 
 * Examples:
 * - Prompt/Baseline pages: <BaseLayout type="split">
 * - Policy pages: <BaseLayout type="tabs">
 */
import React from 'react';
import { ContentGrid } from '../ContentBlock/ContentGrid';
import { Tabs, TabPanel } from '../Tabs';
import styles from './BaseLayout.module.css';

export type BaseLayoutType = 'split' | 'tabs';

export interface BaseLayoutProps {
  /** Layout type */
  type: BaseLayoutType;
  /** Layout content */
  children: React.ReactNode;
  /** Additional CSS class */
  className?: string;
}

/**
 * Split layout - two columns for container + version
 * Used by PromptEditorPage, BaselineEditorPage
 */
export interface SplitLayoutProps {
  /** Left column content (container info) */
  left: React.ReactNode;
  /** Right column content (version/status) */
  right: React.ReactNode;
  /** Gap between columns */
  gap?: 'sm' | 'md' | 'lg';
  /** Additional CSS class */
  className?: string;
}

/**
 * Tabs layout - tabbed interface
 * Used by PolicyEditorPage
 */
export interface TabsLayoutProps {
  /** Tab configuration */
  tabs: Array<{
    id: string;
    label: string;
    content: React.ReactNode;
  }>;
  /** Active tab ID */
  activeTab?: string;
  /** On tab change callback */
  onTabChange?: (tabId: string) => void;
  /** Additional CSS class */
  className?: string;
}

export function BaseLayout({ type, children, className = '' }: BaseLayoutProps) {
  return (
    <div className={`${styles.baseLayout} ${styles[`layout-${type}`]} ${className}`}>
      {children}
    </div>
  );
}

/**
 * Split layout component
 */
export function SplitLayout({ left, right, gap = 'md', className = '' }: SplitLayoutProps) {
  return (
    <BaseLayout type="split" className={className}>
      <ContentGrid gap={gap} direction="row">
        <div className={styles.splitLeft}>{left}</div>
        <div className={styles.splitRight}>{right}</div>
      </ContentGrid>
    </BaseLayout>
  );
}

/**
 * Tabs layout component
 */
export function TabsLayout({ tabs, activeTab, onTabChange, className = '' }: TabsLayoutProps) {
  const defaultActiveTab = tabs[0]?.id || '';
  const [internalActiveTab, setInternalActiveTab] = React.useState(defaultActiveTab);
  
  const currentActiveTab = activeTab || internalActiveTab;
  const handleTabChange = onTabChange || setInternalActiveTab;

  const tabConfig = tabs.map(tab => ({ id: tab.id, label: tab.label }));

  return (
    <BaseLayout type="tabs" className={className}>
      <Tabs 
        tabs={tabConfig} 
        activeTab={currentActiveTab} 
        onChange={handleTabChange}
      >
        {tabs.map((tab) => (
          <TabPanel id={tab.id} activeTab={currentActiveTab} key={tab.id}>
            {tab.content}
          </TabPanel>
        ))}
      </Tabs>
    </BaseLayout>
  );
}

export default BaseLayout;

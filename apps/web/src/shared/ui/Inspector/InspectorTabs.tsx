import { useEffect, useMemo, useState } from 'react';
import { Tabs } from '@/shared/ui/Tabs';
import styles from './Inspector.module.css';

interface TabDef {
  key: string;
  label: string;
}

interface InspectorTabsProps {
  entityId: string;
  tabs: TabDef[];
  defaultTab?: string;
  render: (activeTab: string) => React.ReactNode;
  onActiveTabChange?: (activeTab: string) => void;
}

export function InspectorTabs({ entityId, tabs, defaultTab = 'info', render, onActiveTabChange }: InspectorTabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab);

  const normalizedTabs = useMemo(
    () => tabs.map((tab) => ({ id: tab.key, label: tab.label })),
    [tabs],
  );

  useEffect(() => {
    setActiveTab(defaultTab);
  }, [entityId, defaultTab]);

  useEffect(() => {
    if (!tabs.some((tab) => tab.key === activeTab)) {
      setActiveTab(defaultTab);
    }
  }, [tabs, activeTab, defaultTab]);

  const handleChange = (tab: string) => {
    setActiveTab(tab);
    onActiveTabChange?.(tab);
  };

  return (
    <Tabs tabs={normalizedTabs} activeTab={activeTab} onChange={handleChange}>
      <div className={styles.tabContent}>{render(activeTab)}</div>
    </Tabs>
  );
}

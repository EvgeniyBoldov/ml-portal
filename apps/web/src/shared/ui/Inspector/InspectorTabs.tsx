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
}

export function InspectorTabs({ entityId, tabs, defaultTab = 'info', render }: InspectorTabsProps) {
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

  return (
    <Tabs tabs={normalizedTabs} activeTab={activeTab} onChange={setActiveTab}>
      <div className={styles.tabContent}>{render(activeTab)}</div>
    </Tabs>
  );
}

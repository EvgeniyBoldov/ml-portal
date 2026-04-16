/**
 * EntityPageV2 - Universal page component with declarative tabs
 * 
 * Architecture:
 *   <EntityPageV2>
 *     <Tab title="Обзор" layout="grid" actions={[...]}>
 *       <EntityInfoBlock />
 *     </Tab>
 *     <Tab title="Версии" layout="full" actions={[...]}>
 *       <VersionsBlock />
 *     </Tab>
 *   </EntityPageV2>
 * 
 * Header renders action buttons from the ACTIVE tab.
 */
import React, { useState, Children, isValidElement } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../Button';
import { Breadcrumbs, type BreadcrumbItem } from '../Breadcrumbs';
import { GridLayout } from '../GridLayout';
import pageStyles from './EntityPage.module.css';

export type EntityPageMode = 'view' | 'edit' | 'create';
export type { BreadcrumbItem };

/* ─── Tab layout types ─── */
export type TabLayout = 
  | 'grid'       // CSS grid with configurable columns (default 1fr 1fr)
  | 'full'       // full width, for tables
  | 'single'     // single centered column (max-width 800px), for create forms
  | 'custom';    // no wrapper, children render as-is

/* ─── Tab component (declarative) ─── */
export interface TabProps {
  /** Tab title shown in tab bar */
  title: string;
  /** Tab ID (auto-generated from index if not provided) */
  id?: string;
  /** Layout type for children */
  layout?: TabLayout;
  /** Grid template columns (only for layout="grid") */
  gridColumns?: string;
  /** Action buttons rendered in header when this tab is active */
  actions?: React.ReactNode[];
  /** Badge (e.g. count) shown next to tab title */
  badge?: React.ReactNode;
  /** Hide this tab */
  hidden?: boolean;
  /** Tab content — existing blocks like EntityInfoBlock, VersionsBlock, etc. */
  children: React.ReactNode;
}

export function Tab(_props: TabProps): React.ReactElement | null {
  // Tab is a declarative component — it doesn't render itself.
  // EntityPageV2 reads its props and renders content.
  return null;
}

/* ─── EntityPageV2 props ─── */
export interface EntityPageV2Props {
  /** Page title */
  title: string;
  /** Page mode */
  mode: EntityPageMode;
  /** Loading state */
  loading?: boolean;
  /** Saving state */
  saving?: boolean;
  /** Breadcrumbs */
  breadcrumbs?: BreadcrumbItem[];
  /** Back path for cancel in create mode */
  backPath?: string;
  /** Additional header actions (always visible) */
  headerActions?: React.ReactNode;
  /** Override all action buttons */
  actionButtons?: React.ReactNode;

  /** Handlers */
  onEdit?: () => void;
  onSave?: () => void;
  onCancel?: () => void;
  onDelete?: () => void;
  showDelete?: boolean;

  /** Default active tab id */
  defaultTab?: string;

  /** Tab children */
  children: React.ReactNode;
}

export function EntityPageV2({
  title,
  mode,
  loading = false,
  saving = false,
  breadcrumbs,
  backPath,
  headerActions,
  actionButtons,
  onEdit,
  onSave,
  onCancel,
  onDelete,
  showDelete = false,
  defaultTab,
  children,
}: EntityPageV2Props) {
  const navigate = useNavigate();

  // Extract Tab props from children
  const tabs: TabProps[] = [];
  Children.forEach(children, (child, index) => {
    if (isValidElement(child) && child.type === Tab) {
      const props = child.props as TabProps;
      tabs.push({
        ...props,
        id: props.id || `tab-${index}`,
      });
    }
  });

  const hasTabs = tabs.length > 1;
  const [activeTabId, setActiveTabId] = useState(defaultTab || tabs[0]?.id || 'tab-0');
  const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0];
  const hasDeclarativeTabActions = tabs.some((tab) => tab.actions !== undefined);

  const isCreate = mode === 'create';
  const isEdit = mode === 'edit';

  // ─── Action buttons ───
  const renderActionButtons = () => {
    if (actionButtons) return actionButtons;

    // New declarative behavior: if page uses Tab actions,
    // header buttons are fully controlled by active tab.
    if (hasDeclarativeTabActions) {
      return activeTab?.actions ?? [];
    }

    const buttons: React.ReactNode[] = [];

    // Mode-based default buttons
    if (isCreate) {
      buttons.push(
        <Button key="cancel" variant="outline" onClick={() => backPath ? navigate(backPath) : onCancel?.()}>
          Отмена
        </Button>,
        <Button key="save" variant="primary" onClick={onSave} disabled={saving}>
          {saving ? 'Создание...' : 'Создать'}
        </Button>,
      );
    } else if (isEdit) {
      buttons.push(
        <Button key="cancel" variant="outline" onClick={onCancel} disabled={saving}>
          Отмена
        </Button>,
        <Button key="save" variant="primary" onClick={onSave} disabled={saving}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </Button>,
      );
    } else {
      if (onEdit) {
        buttons.push(
          <Button key="edit" variant="primary" onClick={onEdit}>
            Редактировать
          </Button>,
        );
      }
    }

    if (showDelete && onDelete && mode === 'view') {
      buttons.push(
        <Button key="delete" variant="danger" onClick={onDelete}>
          Удалить
        </Button>,
      );
    }

    return buttons;
  };

  // ─── Tabs bar ───
  const renderTabsBar = () => {
    if (!hasTabs) return null;

    const visibleTabs = tabs.filter(t => !t.hidden);

    return (
      <div className={pageStyles.tabsSection}>
        {visibleTabs.map(tab => (
          <button
            key={tab.id}
            className={`${pageStyles.tab} ${tab.id === activeTabId ? pageStyles.active : ''}`}
            onClick={() => setActiveTabId(tab.id!)}
            type="button"
          >
            {tab.title}
            {tab.badge !== undefined && (
              <span className={pageStyles.tabCount}>{tab.badge}</span>
            )}
          </button>
        ))}
      </div>
    );
  };

  // ─── Tab content with layout ───
  const renderTabContent = () => {
    if (!activeTab) return null;

    const layout = activeTab.layout || 'grid';

    switch (layout) {
      case 'grid':
        return (
          <div className={pageStyles.overviewTab}>
            <GridLayout>
              {activeTab.children}
            </GridLayout>
          </div>
        );

      case 'full':
        return (
          <div className={pageStyles.versionsTab}>
            {activeTab.children}
          </div>
        );

      case 'single':
        return (
          <div className={pageStyles.createTab}>
            {activeTab.children}
          </div>
        );

      case 'custom':
        return activeTab.children;

      default:
        return activeTab.children;
    }
  };

  return (
    <div className={pageStyles.wrap}>
      {/* Breadcrumbs */}
      {breadcrumbs && breadcrumbs.length > 0 && (
        <div className={pageStyles.breadcrumbs}>
          <Breadcrumbs items={breadcrumbs} />
        </div>
      )}

      {/* Header */}
      <header className={pageStyles.header}>
        <div className={pageStyles.headerLeft}>
          <h1 className={pageStyles.title}>{title}</h1>
          {isEdit && (
            <span className={pageStyles.editBadge}>Редактирование</span>
          )}
        </div>
        <div className={pageStyles.headerRight}>
          {headerActions}
          <div className={pageStyles.actionButtons}>
            {renderActionButtons()}
          </div>
        </div>
      </header>

      {/* Tabs bar */}
      {renderTabsBar()}

      {/* Content */}
      <div className={pageStyles.tabContent}>
        {loading ? (
          <div className={pageStyles.loading}>Загрузка...</div>
        ) : (
          renderTabContent()
        )}
      </div>
    </div>
  );
}

export default EntityPageV2;

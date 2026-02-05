/**
 * EntityTabsPage - Universal wrapper for entity editor pages
 * 
 * REDESIGNED: Tabs in header, proper content background
 */
import React, { useState } from 'react';
import { EntityPage, type EntityPageMode, type BreadcrumbItem } from '../EntityPage';
import { SplitLayout } from '../BaseLayout';
import { EntityInfoBlock } from '../EntityInfoBlock/EntityInfoBlock';
import { VersionsBlock } from '../VersionsBlock/VersionsBlock';
import Button from '../Button';
import { type FieldDefinition } from '../ContentBlock/ContentBlock';
import { type DataTableColumn } from '../DataTable/DataTable';
import styles from './EntityTabsPage.module.css';

export interface EntityTabsPageProps<TContainer, TVersion> {
  // Entity identification
  entityType: 'prompt' | 'baseline' | 'policy';
  entityNameLabel: string; // e.g. "Промпт"
  entityTypeLabel: string; // e.g. "промпта" (genitive case)
  slug: string;
  
  // Paths
  basePath: string; // e.g. "/admin/prompts"
  listPath: string; // e.g. "/admin/prompts"
  
  // Data & API
  container: TContainer | null;
  versions: TVersion[];
  isLoading: boolean;
  
  // Form state
  formData: any;
  mode: EntityPageMode;
  saving: boolean;
  
  // Handlers
  onFieldChange: (key: string, value: any) => void;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onCreateVersion: () => void;
  onSelectVersion: (version: TVersion) => void;
  
  // Configuration
  containerFields: FieldDefinition[];
  breadcrumbs: BreadcrumbItem[];
  
  // Optional customization
  renderVersionContent?: (version: TVersion | null) => React.ReactNode;
  versionColumns?: DataTableColumn<TVersion>[];
  showDelete?: boolean;
  onDelete?: () => void;
}

export function EntityTabsPage<
  TContainer extends { slug: string; name: string },
  TVersion extends { version: number; status: string; created_at: string }
>({
  entityType,
  entityNameLabel,
  entityTypeLabel,
  slug,
  basePath,
  listPath,
  container,
  versions,
  isLoading,
  formData,
  mode,
  saving,
  onFieldChange,
  onEdit,
  onSave,
  onCancel,
  onCreateVersion,
  onSelectVersion,
  containerFields,
  breadcrumbs,
  renderVersionContent,
  versionColumns,
  showDelete = false,
  onDelete,
}: EntityTabsPageProps<TContainer, TVersion>) {
  const isNew = slug === 'new';
  const isEditable = mode === 'edit' || mode === 'create';
  const [activeTab, setActiveTab] = useState('overview');

  // Unified action buttons based on active tab and mode
  const getActionButtons = () => {
    const buttons = [];
    
    if (isNew) {
      // Create mode
      buttons.push(
        <Button key="save" variant="primary" onClick={onSave} disabled={saving}>
          {saving ? 'Сохранение...' : 'Создать'}
        </Button>
      );
      buttons.push(
        <Button key="cancel" variant="secondary" onClick={onCancel}>
          Отмена
        </Button>
      );
    } else if (isEditable) {
      // Edit mode
      if (activeTab === 'overview') {
        buttons.push(
          <Button key="save" variant="primary" onClick={onSave} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        );
        buttons.push(
          <Button key="cancel" variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
        );
      } else if (activeTab === 'versions') {
        buttons.push(
          <Button key="create" variant="primary" onClick={onCreateVersion}>
            Создать версию
          </Button>
        );
      }
      
      if (showDelete && onDelete) {
        buttons.push(
          <Button key="delete" variant="danger" onClick={onDelete}>
            Удалить
          </Button>
        );
      }
    } else {
      // View mode
      if (activeTab === 'overview') {
        buttons.push(
          <Button key="edit" variant="primary" onClick={onEdit}>
            Редактировать
          </Button>
        );
      } else if (activeTab === 'versions') {
        buttons.push(
          <Button key="create" variant="primary" onClick={onCreateVersion}>
            Создать версию
          </Button>
        );
      }
      
      if (showDelete && onDelete) {
        buttons.push(
          <Button key="delete" variant="danger" onClick={onDelete}>
            Удалить
          </Button>
        );
      }
    }
    
    return buttons;
  };

  // Tabs section (between header and content)
  const tabsSection = !isNew && (
    <div className={styles.tabsSection}>
      <button
        className={`${styles.tab} ${activeTab === 'overview' ? styles.active : ''}`}
        onClick={() => setActiveTab('overview')}
      >
        Обзор
      </button>
      <button
        className={`${styles.tab} ${activeTab === 'versions' ? styles.active : ''}`}
        onClick={() => setActiveTab('versions')}
      >
        Версии
        <span className={styles.tabCount}>{versions.length}</span>
      </button>
    </div>
  );

  return (
    <EntityPage
      mode={mode}
      entityName={container?.name || `Новый ${entityNameLabel.toLowerCase()}`}
      entityTypeLabel={entityTypeLabel}
      backPath={listPath}
      breadcrumbs={breadcrumbs}
      loading={!isNew && isLoading}
      saving={saving}
      onEdit={onEdit}
      onSave={onSave}
      onCancel={onCancel}
      showDelete={false}
      onDelete={undefined}
      actionButtons={getActionButtons()}
      tabsBar={tabsSection}
      noPadding={!isNew}
    >
      {isNew ? (
        // Create mode - simple entity info
        <div className={styles.content}>
          <EntityInfoBlock
            entity={formData}
            entityType={entityType}
            editable={true}
            fields={containerFields}
            onFieldChange={onFieldChange}
          />
        </div>
      ) : (
        // Edit/View mode - tabs with content wrapper
        <div className={styles.tabContent}>
          {activeTab === 'overview' && (
            <SplitLayout
              left={
                <EntityInfoBlock
                  entity={container}
                  entityType={entityType}
                  editable={mode === 'edit'}
                  fields={containerFields}
                  onFieldChange={onFieldChange}
                />
              }
              right={
                <div className={styles.content}>
                  {renderVersionContent ? (
                    renderVersionContent(versions[0] as TVersion)
                  ) : (
                    <div>Version content placeholder</div>
                  )}
                </div>
              }
            />
          )}
          
          {activeTab === 'versions' && (
            <div className={styles.content}>
              <VersionsBlock
                versions={versions}
                onSelectVersion={onSelectVersion}
                columns={versionColumns}
              />
            </div>
          )}
        </div>
      )}
    </EntityPage>
  );
}

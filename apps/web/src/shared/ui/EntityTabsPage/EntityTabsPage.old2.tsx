/**
 * EntityTabsPage - Universal wrapper for entity editor pages
 * 
 * REDESIGNED: Unified action buttons, hanging tabs, better layout
 */
import React, { useState } from 'react';
import { EntityPage, type EntityPageMode, type BreadcrumbItem } from '../EntityPage';
import { TabsLayout } from '../BaseLayout';
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
      showDelete={false} // Убираем дублирование кнопок
      onDelete={undefined}
      actionButtons={getActionButtons()} // Передаем единый блок кнопок
    >
      {isNew ? (
        // Create mode - simple entity info
        <EntityInfoBlock
          entity={formData}
          entityType={entityType}
          editable={true}
          fields={containerFields}
          onFieldChange={onFieldChange}
        />
      ) : (
        // Edit & View modes - tabs layout with hanging tabs
        <div className={styles.tabsContainer}>
          {/* Hanging tabs */}
          <div className={styles.hangingTabs}>
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
              Версии ({versions.length})
            </button>
          </div>

          {/* Tab content */}
          <div className={styles.tabContent}>
            {activeTab === 'overview' && (
              <div className={styles.overviewTab}>
                <SplitLayout
                  left={
                    <EntityInfoBlock
                      entity={formData}
                      entityType={entityType}
                      editable={isEditable}
                      fields={containerFields}
                      onFieldChange={onFieldChange}
                      showStatus={false}
                    />
                  }
                  right={
                    renderVersionContent && versions.length > 0
                      ? renderVersionContent(versions[0] as TVersion)
                      : (
                        <div className={styles.emptyVersion}>
                          <p>Нет версий</p>
                          <Button variant="primary" onClick={onCreateVersion}>
                            Создать версию
                          </Button>
                        </div>
                      )
                  }
                />
              </div>
            )}

            {activeTab === 'versions' && (
              <div className={styles.versionsTab}>
                <VersionsBlock
                  entity={container}
                  entityType={entityType}
                  versions={versions}
                  onSelectVersion={onSelectVersion}
                  columns={versionColumns}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </EntityPage>
  );
}

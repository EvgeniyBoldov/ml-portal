/**
 * EntityTabsPage - Universal wrapper for entity editor pages
 * 
 * REDESIGNED: Tabs in header, proper content background
 */
import React, { useState } from 'react';
import { EntityPage, type EntityPageProps, type EntityPageMode } from '../EntityPage';
import { EntityInfoBlock, type EntityInfo } from '../EntityInfoBlock';
import { ShortEntityBlock, type ShortEntityBlockProps } from '../ShortEntityBlock';
import { ShortVersionCard } from '../VersionCard';
import { VersionsBlock, type VersionInfo } from '../VersionsBlock';
import { SplitLayout } from '../BaseLayout';
import Button from '../Button';
import { type FieldDefinition } from '../ContentBlock/ContentBlock';
import { type DataTableColumn } from '../DataTable/DataTable';
import styles from './EntityTabsPage.module.css';

export interface EntityTabsPageProps<TContainer = any, TVersion = any> {
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
  onSetRecommended?: (version: TVersion) => void;
  
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
  TVersion extends { version: number; status: string; created_at: string; id: string }
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
  onSetRecommended,
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
  const [selectedVersion, setSelectedVersion] = useState<TVersion | null>(null);

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
        <Button key="cancel" variant="outline" onClick={onCancel}>
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
          <Button key="cancel" variant="outline" onClick={onCancel}>
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
        
        // Add "Set as Recommended" button if we have a selected version that's active but not recommended
        if (selectedVersion && selectedVersion.status === 'active' && selectedVersion.id !== container?.recommended_version?.id && onSetRecommended) {
          buttons.push(
            <Button 
              key="setRecommended" 
              variant="outline" 
              onClick={() => onSetRecommended(selectedVersion)}
            >
              Сделать основной
            </Button>
          );
        }
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
        // Create mode - single column layout
        <div className={styles.createTab}>
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
            <div className={styles.overviewTab}>
              <div className={styles.splitLayout}>
                <div className={styles.splitLeft}>
                  <EntityInfoBlock
                    entity={container}
                    entityType={entityType}
                    editable={mode === 'edit'}
                    fields={containerFields}
                    onFieldChange={onFieldChange}
                  />
                </div>
                <div className={styles.splitRight}>
                  {container?.recommended_version ? (
                    <ShortEntityBlock
                      title="Основная версия"
                      subtitle={`Версия ${container.recommended_version.version}`}
                      items={[
                        { label: 'Статус', value: container.recommended_version.status },
                        { label: 'Создана', value: new Date(container.recommended_version.created_at).toLocaleDateString('ru-RU') },
                      ]}
                    >
                      <ShortVersionCard
                        entityType={entityType}
                        version={container.recommended_version}
                      />
                    </ShortEntityBlock>
                  ) : (
                    <ShortEntityBlock
                      title="Основная версия"
                      subtitle="Нет основной версии"
                      items={[
                        { label: 'Статус', value: '—' },
                        { label: 'Создана', value: '—' },
                      ]}
                    />
                  )}
                </div>
              </div>
            </div>
          )}
          
          {activeTab === 'versions' && (
            <div className={styles.versionsTab}>
              <VersionsBlock
                entityType={entityType}
                versions={versions}
                onSelectVersion={(version) => {
                  setSelectedVersion(version);
                  onSelectVersion?.(version);
                }}
                selectedVersion={selectedVersion}
                recommendedVersionId={container?.recommended_version?.id}
                onSetRecommended={onSetRecommended}
                columns={versionColumns}
              />
            </div>
          )}
        </div>
      )}
    </EntityPage>
  );
}

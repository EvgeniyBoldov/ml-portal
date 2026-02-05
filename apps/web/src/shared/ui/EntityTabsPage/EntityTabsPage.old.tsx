/**
 * EntityTabsPage - Universal wrapper for entity editor pages
 * 
 * Standardizes layout for Prompt, Baseline, Policy editor pages
 * Reduces code duplication from ~400 lines to ~50 lines per page
 */
import React from 'react';
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
      showDelete={showDelete}
      onDelete={onDelete}
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
        // Edit & View modes - tabs layout
        <TabsLayout
          tabs={[
            {
              id: 'overview',
              label: 'Обзор',
              content: (
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
              ),
            },
            {
              id: 'versions',
              label: `Версии (${versions.length})`,
              content: (
                <div className={styles.versionsTab}>
                  <div className={styles.versionsHeader}>
                    <Button variant="primary" onClick={onCreateVersion}>
                      Создать версию
                    </Button>
                  </div>
                  <VersionsBlock
                    entityType={entityType}
                    versions={versions as any}
                    onSelectVersion={onSelectVersion as any}
                    columns={versionColumns}
                  />
                </div>
              ),
            },
          ]}
        />
      )}
    </EntityPage>
  );
}

export default EntityTabsPage;

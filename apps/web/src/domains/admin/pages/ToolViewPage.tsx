/**
 * ToolViewPage - View tool details
 * 
 * Layout similar to PromptEditorPage:
 * - Left column (1/2): Tool info (readonly)
 * - Right column (1/2): Input/Output schemas
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolsApi, type Tool } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { EntityPage, type EntityPageMode } from '@/shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@/shared/ui/ContentBlock';
import Badge from '@/shared/ui/Badge';
import styles from './PromptEditorPage.module.css';

const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  function: 'Функция',
  database: 'База данных',
  builtin: 'Встроенный',
};

const TYPE_TONES: Record<string, 'warn' | 'success' | 'info' | 'neutral'> = {
  api: 'info',
  function: 'success',
  database: 'warn',
  builtin: 'neutral',
};

export function ToolViewPage() {
  const { groupId, toolSlug } = useParams<{ groupId: string; toolSlug: string }>();
  const navigate = useNavigate();
  
  const { data: tool, isLoading } = useQuery({
    queryKey: qk.tools.detail(toolSlug!),
    queryFn: () => toolsApi.get(toolSlug!),
    enabled: !!toolSlug,
  });

  // Back path to group
  const backPath = groupId ? `/admin/tools/groups/${groupId}` : '/admin/tools';

  // Field definitions (readonly)
  const toolFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      disabled: true,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      disabled: true,
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      disabled: true,
      rows: 2,
    },
  ];

  const formData = tool ? {
    slug: tool.slug,
    name: tool.name,
    description: tool.description || '',
  } : { slug: '', name: '', description: '' };

  return (
    <EntityPage
      mode="view"
      entityName={tool?.name || 'Инструмент'}
      entityTypeLabel="инструмента"
      backPath={backPath}
      loading={isLoading}
      showDelete={false}
    >
      <ContentGrid>
        {/* Tool Info - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Информация об инструменте"
          icon="tool"
          fields={toolFields}
          data={formData}
        >
          {/* Type and Status badges */}
          {tool && (
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <Badge tone={TYPE_TONES[tool.type] || 'neutral'}>
                {TYPE_LABELS[tool.type] || tool.type}
              </Badge>
              <Badge tone={tool.is_active ? 'success' : 'neutral'}>
                {tool.is_active ? 'Активен' : 'Неактивен'}
              </Badge>
            </div>
          )}
        </ContentBlock>

        {/* Schemas - 1/2 */}
        <ContentBlock
          width="1/2"
          title="Схемы данных"
          icon="code"
        >
          {tool?.input_schema && Object.keys(tool.input_schema).length > 0 && (
            <>
              <h4 style={{ fontSize: '0.875rem', marginBottom: '0.5rem', color: 'var(--muted)' }}>
                Входные данные
              </h4>
              <pre className={styles.templateBlock} style={{ marginBottom: '1rem' }}>
                {JSON.stringify(tool.input_schema, null, 2)}
              </pre>
            </>
          )}
          
          {tool?.output_schema && Object.keys(tool.output_schema).length > 0 && (
            <>
              <h4 style={{ fontSize: '0.875rem', marginBottom: '0.5rem', color: 'var(--muted)' }}>
                Выходные данные
              </h4>
              <pre className={styles.templateBlock}>
                {JSON.stringify(tool.output_schema, null, 2)}
              </pre>
            </>
          )}
          
          {(!tool?.input_schema || Object.keys(tool.input_schema).length === 0) && 
           (!tool?.output_schema || Object.keys(tool.output_schema).length === 0) && (
            <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>
              Схемы данных не определены.
            </p>
          )}
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}

export default ToolViewPage;

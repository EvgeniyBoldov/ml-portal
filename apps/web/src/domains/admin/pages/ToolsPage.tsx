/**
 * ToolsPage - Реестр инструментов
 * 
 * Инструменты загружаются из бэкенда (sync_tools_from_registry).
 * Клик по строке → страница просмотра/редактирования.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolsApi, type Tool } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './RegistryPage.module.css';

const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  function: 'Функция',
  database: 'База данных',
  builtin: 'Встроенный',
};

const TYPE_TONES: Record<string, 'info' | 'success' | 'warning' | 'neutral'> = {
  api: 'info',
  function: 'success',
  database: 'warning',
  builtin: 'neutral',
};

function ToolRow({ 
  tool,
  onClick
}: { 
  tool: Tool;
  onClick: () => void;
}) {
  return (
    <tr onClick={onClick} style={{ cursor: 'pointer' }}>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{tool.slug}</span>
          <span className={styles.cellSecondary}>{tool.name}</span>
        </div>
      </td>
      <td>
        <Badge tone={TYPE_TONES[tool.type] || 'neutral'}>
          {TYPE_LABELS[tool.type] || tool.type}
        </Badge>
      </td>
      <td>
        <span className={styles.cellSecondary} style={{ maxWidth: '300px', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {tool.description || '—'}
        </span>
      </td>
      <td>
        <Badge tone={tool.is_active ? 'success' : 'neutral'} size="small">
          {tool.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      </td>
    </tr>
  );
}

export function ToolsPage() {
  const [q, setQ] = useState('');
  const navigate = useNavigate();
  
  const { data: tools, isLoading, error } = useQuery({
    queryKey: qk.tools.list({ q: q || undefined }),
    queryFn: () => toolsApi.list(),
    staleTime: 60000,
  });

  const filteredTools = tools?.filter((t: Tool) => 
    t.name.toLowerCase().includes(q.toLowerCase()) || 
    t.slug.toLowerCase().includes(q.toLowerCase()) ||
    (t.description?.toLowerCase().includes(q.toLowerCase()))
  ) || [];

  const handleRowClick = (tool: Tool) => {
    navigate(`/admin/tools/${tool.slug}`);
  };

  return (
    <AdminPage
      title="Инструменты"
      subtitle="Доступные инструменты для агентов (загружаются из бэкенда)"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск инструментов..."
    >
      {error && (
        <div className={styles.errorState}>
          Не удалось загрузить инструменты. Попробуйте снова.
        </div>
      )}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>SLUG / ИМЯ</th>
              <th>ТИП</th>
              <th>ОПИСАНИЕ</th>
              <th>СТАТУС</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 4 }).map((__, j) => (
                    <td key={j}>
                      <Skeleton width={j === 0 ? 200 : 100} />
                    </td>
                  ))}
                </tr>
              ))
            ) : filteredTools.length === 0 ? (
              <tr>
                <td colSpan={4} className={styles.emptyState}>
                  Инструменты не найдены.
                </td>
              </tr>
            ) : (
              filteredTools.map((tool: Tool) => (
                <ToolRow 
                  key={tool.id} 
                  tool={tool} 
                  onClick={() => handleRowClick(tool)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </AdminPage>
  );
}

export default ToolsPage;

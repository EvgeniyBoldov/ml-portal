/**
 * ToolsPage - Реестр инструментов (Read-Only)
 * 
 * Инструменты загружаются из бэкенда (sync_tools_from_registry).
 * Веб только отображает информацию, без возможности редактирования.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toolsApi, type Tool } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
import Modal from '@/shared/ui/Modal';
import Button from '@/shared/ui/Button';
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
  onSelect
}: { 
  tool: Tool;
  onSelect: (tool: Tool) => void;
}) {
  return (
    <tr onClick={() => onSelect(tool)} style={{ cursor: 'pointer' }}>
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

function ToolDetailModal({ tool, onClose }: { tool: Tool | null; onClose: () => void }) {
  if (!tool) return null;
  
  return (
    <Modal open={!!tool} onClose={onClose} title={tool.name}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div>
          <strong>Slug:</strong> <code>{tool.slug}</code>
        </div>
        <div>
          <strong>Тип:</strong>{' '}
          <Badge tone={TYPE_TONES[tool.type] || 'neutral'}>
            {TYPE_LABELS[tool.type] || tool.type}
          </Badge>
        </div>
        <div>
          <strong>Статус:</strong>{' '}
          <Badge tone={tool.is_active ? 'success' : 'neutral'}>
            {tool.is_active ? 'Активен' : 'Неактивен'}
          </Badge>
        </div>
        {tool.description && (
          <div>
            <strong>Описание:</strong>
            <p style={{ margin: '8px 0', color: 'var(--muted)' }}>{tool.description}</p>
          </div>
        )}
        <div>
          <strong>Входная схема (input_schema):</strong>
          <pre style={{ 
            background: 'var(--bg-hover)', 
            padding: '12px', 
            borderRadius: 'var(--radius)',
            overflow: 'auto',
            maxHeight: '200px',
            fontSize: '0.85em'
          }}>
            {JSON.stringify(tool.input_schema, null, 2)}
          </pre>
        </div>
        {tool.output_schema && (
          <div>
            <strong>Выходная схема (output_schema):</strong>
            <pre style={{ 
              background: 'var(--bg-hover)', 
              padding: '12px', 
              borderRadius: 'var(--radius)',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: '0.85em'
            }}>
              {JSON.stringify(tool.output_schema, null, 2)}
            </pre>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
          <Button variant="outline" onClick={onClose}>Закрыть</Button>
        </div>
      </div>
    </Modal>
  );
}

export function ToolsPage() {
  const [q, setQ] = useState('');
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  
  const { data: tools, isLoading, error } = useQuery({
    queryKey: qk.tools.list({ q: q || undefined }),
    queryFn: () => toolsApi.list(),
    staleTime: 60000,
  });

  const filteredTools = tools?.filter(t => 
    t.name.toLowerCase().includes(q.toLowerCase()) || 
    t.slug.toLowerCase().includes(q.toLowerCase()) ||
    (t.description?.toLowerCase().includes(q.toLowerCase()))
  ) || [];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Инструменты</h1>
            <p className={styles.subtitle}>
              Доступные инструменты для агентов (загружаются из бэкенда)
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск инструментов..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
          </div>
        </div>

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
                filteredTools.map(tool => (
                  <ToolRow 
                    key={tool.id} 
                    tool={tool} 
                    onSelect={setSelectedTool}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      
      <ToolDetailModal tool={selectedTool} onClose={() => setSelectedTool(null)} />
    </div>
  );
}

export default ToolsPage;

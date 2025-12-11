import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { toolsApi, Tool } from '@/shared/api';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
// Reuse styles from prompts page as they are identical in structure
import styles from './PromptRegistryPage.module.css';

function ToolRow({ tool }: { tool: Tool }) {
  return (
    <tr>
      <td>
        <div className={styles.modelName}>
          <div style={{ fontWeight: 500 }}>{tool.slug}</div>
          <div style={{ fontSize: '0.85em', color: '#666' }}>{tool.name}</div>
        </div>
      </td>
      <td>
        <Badge tone="info">{tool.type}</Badge>
      </td>
      <td>
        {/* Tools don't have versions in UI yet */}
        <span style={{ color: '#999' }}>—</span>
      </td>
      <td>
        <span className={styles.updatedAt}>
          {new Date(tool.updated_at).toLocaleDateString()}
        </span>
      </td>
      <td>
        <div className={styles.actions}>
          <Link to={`/admin/tools/${tool.slug}`}>
            <Button variant="outline" size="sm">Редактировать</Button>
          </Link>
        </div>
      </td>
    </tr>
  );
}

export function ToolsPage() {
  const [q, setQ] = useState('');
  
  const { data: tools, isLoading, error } = useQuery({
    queryKey: ['tools', 'list'],
    queryFn: () => toolsApi.list(),
  });

  const filteredTools = tools?.filter(t => 
    t.name.toLowerCase().includes(q.toLowerCase()) || 
    t.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Реестр Инструментов</h1>
            <p style={{ color: 'var(--muted)', fontSize: '0.9em', marginTop: '4px' }}>
              Управление внешними инструментами, API вызовами и функциями для агентов.
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Search tools..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/tools/new">
              <Button variant="primary">Создать Инструмент</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div style={{ color: 'var(--danger)', padding: '12px' }}>
            Failed to load tools. Please try again.
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG / NAME</th>
                <th>TYPE</th>
                <th>VERSION</th>
                <th>UPDATED</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 5 }).map((__, j) => (
                      <td key={j}>
                        <Skeleton width={j === 0 ? 200 : 100} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filteredTools.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyState}>
                    Нет созданных инструментов
                  </td>
                </tr>
              ) : (
                filteredTools.map(tool => (
                  <ToolRow key={tool.id} tool={tool} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

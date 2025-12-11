import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { promptsApi, Prompt } from '@/shared/api';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './PromptRegistryPage.module.css';

function PromptRow({ prompt }: { prompt: Prompt }) {
  return (
    <tr>
      <td>
        <div className={styles.modelName}>
          <div style={{ fontWeight: 500 }}>{prompt.slug}</div>
          <div style={{ fontSize: '0.85em', color: '#666' }}>{prompt.name}</div>
        </div>
      </td>
      <td>
        <Badge tone="info">{prompt.type}</Badge>
      </td>
      <td>
        <span className={styles.version}>v{prompt.version}</span>
      </td>
      <td>
        <span className={styles.updatedAt}>
          {new Date(prompt.updated_at).toLocaleDateString()}
        </span>
      </td>
      <td>
        <div className={styles.actions}>
          <Link to={`/admin/prompts/${prompt.slug}`}>
            <Button variant="outline" size="sm">Редактировать</Button>
          </Link>
        </div>
      </td>
    </tr>
  );
}

export function PromptRegistryPage() {
  const [q, setQ] = useState('');
  
  const { data: prompts, isLoading, error } = useQuery({
    queryKey: ['prompts', 'list'],
    queryFn: () => promptsApi.list(),
  });

  const filteredPrompts = prompts?.filter(p => 
    p.name.toLowerCase().includes(q.toLowerCase()) || 
    p.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Реестр Промптов</h1>
            <p style={{ color: 'var(--muted)', fontSize: '0.9em', marginTop: '4px' }}>
              Управление шаблонами LLM промптов и их версиями.
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Search prompts..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/prompts/new">
              <Button variant="primary">Создать Промпт</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div style={{ color: 'var(--danger)', padding: '12px' }}>
            Failed to load prompts. Please try again.
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
              ) : filteredPrompts.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyState}>
                    Нет созданных промптов
                  </td>
                </tr>
              ) : (
                filteredPrompts.map(prompt => (
                  <PromptRow key={prompt.id} prompt={prompt} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

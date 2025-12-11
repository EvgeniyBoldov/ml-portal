import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { agentsApi, Agent } from '@/shared/api';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './PromptRegistryPage.module.css';

function AgentRow({ agent }: { agent: Agent }) {
  return (
    <tr>
      <td>
        <div className={styles.modelName}>
          <div style={{ fontWeight: 500 }}>{agent.slug}</div>
          <div style={{ fontSize: '0.85em', color: '#666' }}>{agent.name}</div>
        </div>
      </td>
      <td>
        <Badge tone="success">v1</Badge>
      </td>
      <td>
        <span className={styles.version}>{agent.system_prompt_slug}</span>
      </td>
      <td>
        <span className={styles.updatedAt}>
          {new Date(agent.updated_at).toLocaleDateString()}
        </span>
      </td>
      <td>
        <div className={styles.actions}>
          <Link to={`/admin/agents/${agent.slug}`}>
            <Button variant="outline" size="sm">Редактировать</Button>
          </Link>
        </div>
      </td>
    </tr>
  );
}

export function AgentRegistryPage() {
  const [q, setQ] = useState('');
  
  const { data: agents, isLoading, error } = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: () => agentsApi.list(),
  });

  const filteredAgents = agents?.filter(a => 
    a.name.toLowerCase().includes(q.toLowerCase()) || 
    a.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Реестр Агентов</h1>
            <p style={{ color: 'var(--muted)', fontSize: '0.9em', marginTop: '4px' }}>
              Сборка Агентов (System Prompt + Tools) для чата и IDE.
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Search agents..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/agents/new">
              <Button variant="primary">Создать Агента</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div style={{ color: 'var(--danger)', padding: '12px' }}>
            Failed to load agents. Please try again.
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG / NAME</th>
                <th>STATUS</th>
                <th>SYSTEM PROMPT</th>
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
              ) : filteredAgents.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyState}>
                    Нет созданных агентов
                  </td>
                </tr>
              ) : (
                filteredAgents.map(agent => (
                  <AgentRow key={agent.id} agent={agent} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

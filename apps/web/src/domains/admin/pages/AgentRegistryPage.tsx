import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { agentsApi, Agent } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './AgentRegistryPage.module.css';

function AgentRow({ agent }: { agent: Agent }) {
  const toolsCount = agent.tools?.length || 0;
  
  return (
    <tr>
      <td>
        <div className={styles.agentName}>
          <span className={styles.agentSlug}>{agent.slug}</span>
          <span className={styles.agentDisplayName}>{agent.name}</span>
        </div>
      </td>
      <td>
        <Badge tone={agent.is_active ? 'success' : 'neutral'}>
          {agent.is_active ? 'Active' : 'Inactive'}
        </Badge>
      </td>
      <td>
        <code className={styles.promptSlug}>{agent.system_prompt_slug}</code>
      </td>
      <td>
        <div className={styles.toolsList}>
          {toolsCount > 0 ? (
            <Badge tone="info" size="small">{toolsCount} tools</Badge>
          ) : (
            <span className={styles.updatedAt}>—</span>
          )}
        </div>
      </td>
      <td>
        <span className={styles.updatedAt}>
          {new Date(agent.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
      <td>
        <div className={styles.actions}>
          <Link to={`/admin/agents/${agent.slug}`}>
            <Button variant="outline" size="sm">Edit</Button>
          </Link>
        </div>
      </td>
    </tr>
  );
}

export function AgentRegistryPage() {
  const [q, setQ] = useState('');
  
  const { data: agents, isLoading, error } = useQuery({
    queryKey: qk.agents.list({ q: q || undefined }),
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
            <h1 className={styles.title}>Agent Registry</h1>
            <p className={styles.subtitle}>
              Agent profiles: System Prompt + Tools for Chat and IDE.
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
              <Button>Create Agent</Button>
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
                <th>TOOLS</th>
                <th>UPDATED</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <td key={j}>
                        <Skeleton width={j === 0 ? 200 : 100} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filteredAgents.length === 0 ? (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    No agents found. Create one to get started.
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

/**
 * AgentRegistryPage - Реестр агентов
 * 
 * Управление профилями агентов: системный промпт + инструменты.
 * Единый стиль с остальными админ-реестрами.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { agentsApi, type Agent } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { ActionsButton, type ActionItem } from '@/shared/ui/ActionsButton';
import { useAppStore } from '@/app/store/app.store';
import styles from './RegistryPage.module.css';

function AgentRow({ 
  agent, 
  getActions 
}: { 
  agent: Agent;
  getActions: (agent: Agent) => ActionItem[];
}) {
  const toolsCount = agent.tools?.length || 0;
  
  return (
    <tr>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{agent.slug}</span>
          <span className={styles.cellSecondary}>{agent.name}</span>
        </div>
      </td>
      <td>
        <Badge tone={agent.is_active ? 'success' : 'neutral'} size="small">
          {agent.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      </td>
      <td>
        <code className={styles.code}>{agent.system_prompt_slug}</code>
      </td>
      <td>
        {toolsCount > 0 ? (
          <Badge tone="info" size="small">{toolsCount} инстр.</Badge>
        ) : (
          <span className={styles.muted}>—</span>
        )}
      </td>
      <td>
        <span className={styles.muted}>
          {new Date(agent.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
      <td>
        <ActionsButton actions={getActions(agent)} />
      </td>
    </tr>
  );
}

export function AgentRegistryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  
  const [q, setQ] = useState('');
  
  const { data: agents, isLoading, error } = useQuery({
    queryKey: qk.agents.list({ q: q || undefined }),
    queryFn: () => agentsApi.list(),
    staleTime: 60000,
  });

  const deleteAgentMutation = useMutation({
    mutationFn: (slug: string) => agentsApi.delete(slug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.agents.all() }),
  });

  const filteredAgents = agents?.filter(a => 
    a.name.toLowerCase().includes(q.toLowerCase()) || 
    a.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  const handleDelete = (agent: Agent) => {
    showConfirmDialog({
      title: `Удалить агента «${agent.slug}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Агент будет удалён"
          description="Удаление нельзя отменить. Чаты, использующие этого агента, перестанут работать."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteAgentMutation.mutateAsync(agent.slug);
          showSuccess(`Агент ${agent.slug} удалён`);
        } catch (err) {
          console.error(err);
          showError('Не удалось удалить агента');
        }
      },
    });
  };

  const getActions = (agent: Agent): ActionItem[] => [
    {
      label: 'Редактировать',
      onClick: () => navigate(`/admin/agents/${agent.slug}`),
    },
    {
      label: 'Дублировать',
      onClick: () => navigate(`/admin/agents/new?from=${agent.slug}`),
    },
    {
      label: 'Удалить',
      onClick: () => handleDelete(agent),
      danger: true,
    },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Агенты</h1>
            <p className={styles.subtitle}>
              Профили агентов: системный промпт + инструменты
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск агентов..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/agents/new">
              <Button>Создать агента</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div className={styles.errorState}>
            Не удалось загрузить агентов. Попробуйте снова.
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG / ИМЯ</th>
                <th>СТАТУС</th>
                <th>ПРОМПТ</th>
                <th>ИНСТРУМЕНТЫ</th>
                <th>ОБНОВЛЁН</th>
                <th>ДЕЙСТВИЯ</th>
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
                    Агенты не найдены. Нажмите «Создать агента» для создания.
                  </td>
                </tr>
              ) : (
                filteredAgents.map(agent => (
                  <AgentRow 
                    key={agent.id} 
                    agent={agent} 
                    getActions={getActions}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default AgentRegistryPage;

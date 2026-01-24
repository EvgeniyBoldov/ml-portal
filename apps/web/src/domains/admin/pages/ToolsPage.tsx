/**
 * ToolsPage - Реестр инструментов
 * 
 * Управление внешними инструментами, API вызовами и функциями для агентов.
 * Единый стиль с остальными админ-реестрами.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { toolsApi, type Tool } from '@/shared/api';
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

const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  function: 'Функция',
  database: 'База данных',
};

function ToolRow({ 
  tool, 
  getActions 
}: { 
  tool: Tool;
  getActions: (tool: Tool) => ActionItem[];
}) {
  return (
    <tr>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{tool.slug}</span>
          <span className={styles.cellSecondary}>{tool.name}</span>
        </div>
      </td>
      <td>
        <Badge tone="info">{TYPE_LABELS[tool.type] || tool.type}</Badge>
      </td>
      <td>
        <Badge tone={tool.is_active ? 'success' : 'neutral'} size="small">
          {tool.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      </td>
      <td>
        <span className={styles.muted}>
          {new Date(tool.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
      <td>
        <ActionsButton actions={getActions(tool)} />
      </td>
    </tr>
  );
}

export function ToolsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  
  const [q, setQ] = useState('');
  
  const { data: tools, isLoading, error } = useQuery({
    queryKey: qk.tools.list({ q: q || undefined }),
    queryFn: () => toolsApi.list(),
    staleTime: 60000,
  });

  const deleteToolMutation = useMutation({
    mutationFn: (slug: string) => toolsApi.delete(slug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.tools.all() }),
  });

  const filteredTools = tools?.filter(t => 
    t.name.toLowerCase().includes(q.toLowerCase()) || 
    t.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  const handleDelete = (tool: Tool) => {
    showConfirmDialog({
      title: `Удалить инструмент «${tool.slug}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Инструмент будет удалён"
          description="Удаление нельзя отменить. Агенты, использующие этот инструмент, перестанут работать."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteToolMutation.mutateAsync(tool.slug);
          showSuccess(`Инструмент ${tool.slug} удалён`);
        } catch (err) {
          console.error(err);
          showError('Не удалось удалить инструмент');
        }
      },
    });
  };

  const getActions = (tool: Tool): ActionItem[] => [
    {
      label: 'Редактировать',
      onClick: () => navigate(`/admin/tools/${tool.slug}`),
    },
    {
      label: 'Дублировать',
      onClick: () => navigate(`/admin/tools/new?from=${tool.slug}`),
    },
    {
      label: 'Удалить',
      onClick: () => handleDelete(tool),
      variant: 'danger',
    },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Инструменты</h1>
            <p className={styles.subtitle}>
              Управление внешними инструментами и API вызовами
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск инструментов..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/tools/new">
              <Button>Создать инструмент</Button>
            </Link>
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
                <th>СТАТУС</th>
                <th>ОБНОВЛЁН</th>
                <th>ДЕЙСТВИЯ</th>
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
                    Инструменты не найдены. Нажмите «Создать инструмент» для создания.
                  </td>
                </tr>
              ) : (
                filteredTools.map(tool => (
                  <ToolRow 
                    key={tool.id} 
                    tool={tool} 
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

export default ToolsPage;

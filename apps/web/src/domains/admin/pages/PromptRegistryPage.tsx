/**
 * PromptRegistryPage - Реестр промптов
 * 
 * Управление системными промптами и их версиями.
 * Единый стиль с остальными админ-реестрами.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { promptsApi, type Prompt } from '@/shared/api';
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
  chat: 'Чат',
  agent: 'Агент',
  task: 'Задача',
  system: 'Системный',
};

function PromptRow({ 
  prompt, 
  getActions 
}: { 
  prompt: Prompt;
  getActions: (prompt: Prompt) => ActionItem[];
}) {
  return (
    <tr>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{prompt.slug}</span>
          <span className={styles.cellSecondary}>{prompt.name}</span>
        </div>
      </td>
      <td>
        <Badge tone="info">{TYPE_LABELS[prompt.type] || prompt.type}</Badge>
      </td>
      <td>
        <code className={styles.code}>v{prompt.version}</code>
      </td>
      <td>
        <Badge tone={prompt.is_active ? 'success' : 'neutral'} size="small">
          {prompt.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      </td>
      <td>
        <span className={styles.muted}>
          {new Date(prompt.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
      <td>
        <ActionsButton actions={getActions(prompt)} />
      </td>
    </tr>
  );
}

export function PromptRegistryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  
  const [q, setQ] = useState('');
  
  const { data: prompts, isLoading, error } = useQuery({
    queryKey: qk.prompts.list({ q: q || undefined }),
    queryFn: () => promptsApi.list(),
    staleTime: 60000,
  });

  // TODO: Добавить deletePrompt в API когда будет готов бэкенд
  // const deletePromptMutation = useMutation({
  //   mutationFn: (slug: string) => promptsApi.delete(slug),
  //   onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.prompts.all() }),
  // });

  const filteredPrompts = prompts?.filter(p => 
    p.name.toLowerCase().includes(q.toLowerCase()) || 
    p.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  const handleDelete = (prompt: Prompt) => {
    showConfirmDialog({
      title: `Удалить промпт «${prompt.slug}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Промпт будет удалён"
          description="Удаление нельзя отменить. Агенты, использующие этот промпт, перестанут работать."
        />
      ),
      onConfirm: async () => {
        try {
          // await deletePromptMutation.mutateAsync(prompt.slug);
          showSuccess(`Промпт ${prompt.slug} удалён`);
          queryClient.invalidateQueries({ queryKey: qk.prompts.all() });
        } catch (err) {
          console.error(err);
          showError('Не удалось удалить промпт');
        }
      },
    });
  };

  const getActions = (prompt: Prompt): ActionItem[] => [
    {
      label: 'Редактировать',
      onClick: () => navigate(`/admin/prompts/${prompt.slug}`),
    },
    {
      label: 'Дублировать',
      onClick: () => navigate(`/admin/prompts/new?from=${prompt.slug}`),
    },
    {
      label: 'Удалить',
      onClick: () => handleDelete(prompt),
      danger: true,
    },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Промпты</h1>
            <p className={styles.subtitle}>
              Управление системными промптами и их версиями
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск промптов..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/prompts/new">
              <Button>Создать промпт</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div className={styles.errorState}>
            Не удалось загрузить промпты. Попробуйте снова.
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG / ИМЯ</th>
                <th>ТИП</th>
                <th>ВЕРСИЯ</th>
                <th>СТАТУС</th>
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
              ) : filteredPrompts.length === 0 ? (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    Промпты не найдены. Нажмите «Создать промпт» для создания.
                  </td>
                </tr>
              ) : (
                filteredPrompts.map(prompt => (
                  <PromptRow 
                    key={prompt.id} 
                    prompt={prompt} 
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

export default PromptRegistryPage;

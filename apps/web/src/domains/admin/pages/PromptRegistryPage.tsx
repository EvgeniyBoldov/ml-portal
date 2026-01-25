/**
 * PromptRegistryPage - Реестр промптов
 * 
 * Список промптов с агрегированной информацией о версиях.
 * Клик по промпту открывает детальную страницу с версиями.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { promptsApi, type PromptListItem, type PromptType } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './RegistryPage.module.css';

const TYPE_LABELS: Record<PromptType, string> = {
  prompt: 'Промпт',
  baseline: 'Бейслайн',
};

const TYPE_TONES: Record<PromptType, 'info' | 'warning'> = {
  prompt: 'info',
  baseline: 'warning',
};

function PromptRow({ prompt }: { prompt: PromptListItem }) {
  const navigate = useNavigate();
  
  return (
    <tr 
      onClick={() => navigate(`/admin/prompts/${prompt.slug}`)}
      style={{ cursor: 'pointer' }}
    >
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{prompt.slug}</span>
          <span className={styles.cellSecondary}>{prompt.name}</span>
        </div>
      </td>
      <td>
        <Badge tone={TYPE_TONES[prompt.type]}>
          {TYPE_LABELS[prompt.type]}
        </Badge>
      </td>
      <td>
        <div className={styles.cellStack}>
          <span>
            <code className={styles.code}>v{prompt.latest_version}</code>
            {prompt.versions_count > 1 && (
              <span className={styles.muted}> ({prompt.versions_count} версий)</span>
            )}
          </span>
          {prompt.active_version && (
            <span className={styles.cellSecondary}>
              Активная: v{prompt.active_version}
            </span>
          )}
        </div>
      </td>
      <td>
        {prompt.active_version ? (
          <Badge tone="success" size="small">Активен</Badge>
        ) : (
          <Badge tone="neutral" size="small">Черновик</Badge>
        )}
      </td>
      <td>
        <span className={styles.muted}>
          {new Date(prompt.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
    </tr>
  );
}

export function PromptRegistryPage() {
  const [q, setQ] = useState('');
  const [typeFilter, setTypeFilter] = useState<PromptType | ''>('');
  
  const { data: prompts, isLoading, error } = useQuery({
    queryKey: qk.prompts.list({ q: q || undefined, type: typeFilter || undefined }),
    queryFn: () => promptsApi.list({ type: typeFilter || undefined }),
    staleTime: 60000,
  });

  const filteredPrompts = prompts?.filter(p => 
    p.name.toLowerCase().includes(q.toLowerCase()) || 
    p.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Промпты</h1>
            <p className={styles.subtitle}>
              Управление системными промптами и бейслайнами
            </p>
          </div>
          <div className={styles.controls}>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as PromptType | '')}
              style={{ 
                padding: '8px 12px', 
                borderRadius: 'var(--radius)', 
                border: '1px solid var(--color-border)',
                background: 'var(--panel)',
                color: 'var(--text)'
              }}
            >
              <option value="">Все типы</option>
              <option value="prompt">Промпты</option>
              <option value="baseline">Бейслайны</option>
            </select>
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
                <th>ВЕРСИИ</th>
                <th>СТАТУС</th>
                <th>ОБНОВЛЁН</th>
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
                    Промпты не найдены. Нажмите «Создать промпт» для создания.
                  </td>
                </tr>
              ) : (
                filteredPrompts.map(prompt => (
                  <PromptRow key={prompt.slug} prompt={prompt} />
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

/**
 * PromptDetailPage - Детальная страница промпта
 * 
 * Структура:
 * - Промпт: название, slug, описание, тип (read-only, редактирование через модалку)
 * - Темплейт: версия, статус, body (редактируется только для draft)
 */
import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { promptsApi, PromptVersionInfo, AgentUsingPrompt } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import Badge from '@/shared/ui/Badge';
import { Skeleton } from '@/shared/ui/Skeleton';
import Modal from '@/shared/ui/Modal';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

import styles from './PromptEditorPage.module.css';

// === КОНСТАНТЫ ===
const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  active: 'Активный',
  archived: 'Архив',
};

const STATUS_TONES: Record<string, 'warn' | 'success' | 'neutral'> = {
  draft: 'warn',
  active: 'success',
  archived: 'neutral',
};

const TYPE_LABELS: Record<string, string> = {
  prompt: 'Промпт',
  baseline: 'Baseline',
};

// === КОМПОНЕНТ ===
export function PromptDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // === STATE ===
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [editedTemplate, setEditedTemplate] = useState('');
  const [hasTemplateChanges, setHasTemplateChanges] = useState(false);
  
  // Модалка редактирования промпта
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', description: '' });

  // === QUERIES ===
  // Список версий (темплейтов)
  const { data: versions, isLoading: versionsLoading } = useQuery({
    queryKey: qk.prompts.versions(slug!),
    queryFn: () => promptsApi.getVersions(slug!),
    enabled: !!slug,
  });

  // Выбранная версия (темплейт)
  const { data: currentTemplate, isLoading: templateLoading } = useQuery({
    queryKey: qk.prompts.version(slug!, selectedVersion!),
    queryFn: () => promptsApi.getVersion(slug!, selectedVersion!),
    enabled: !!slug && selectedVersion !== null,
  });

  // Агенты, использующие промпт
  const { data: agents } = useQuery({
    queryKey: qk.prompts.agents(slug!),
    queryFn: () => promptsApi.getAgents(slug!),
    enabled: !!slug,
  });

  // === EFFECTS ===
  // Автовыбор первой версии
  useEffect(() => {
    if (versions && versions.length > 0 && selectedVersion === null) {
      // Выбираем активную версию или первую
      const activeVersion = versions.find(v => v.status === 'active');
      setSelectedVersion(activeVersion?.version || versions[0].version);
    }
  }, [versions, selectedVersion]);

  // Синхронизация template с выбранной версией
  useEffect(() => {
    if (currentTemplate) {
      setEditedTemplate(currentTemplate.template);
      setHasTemplateChanges(false);
    }
  }, [currentTemplate]);

  // Метаданные промпта (из первой версии)
  const promptMeta = versions?.[0];

  // === MUTATIONS ===
  // Сохранение темплейта (только для draft)
  const saveTemplateMutation = useMutation({
    mutationFn: () => promptsApi.update(currentTemplate!.id, { template: editedTemplate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.version(slug!, selectedVersion!) });
      showSuccess('Темплейт сохранён');
      setHasTemplateChanges(false);
    },
    onError: () => showError('Ошибка сохранения темплейта'),
  });

  // Редактирование промпта (название, описание) - обновляем все версии
  const updatePromptMutation = useMutation({
    mutationFn: async () => {
      if (!versions || versions.length === 0) throw new Error('Нет версий');
      // Обновляем все версии (метаданные общие)
      await Promise.all(
        versions.map((v) =>
          promptsApi.update(v.id, { name: editForm.name, description: editForm.description })
        )
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.versions(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.list({}) });
      showSuccess('Промпт обновлён');
      setShowEditModal(false);
    },
    onError: () => showError('Ошибка обновления промпта'),
  });

  // Активация версии
  const activateMutation = useMutation({
    mutationFn: () => promptsApi.activate(currentTemplate!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.versions(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.version(slug!, selectedVersion!) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.list({}) });
      showSuccess('Версия активирована');
    },
    onError: () => showError('Ошибка активации'),
  });

  // Создание новой версии (копия активной)
  const createVersionMutation = useMutation({
    mutationFn: async () => {
      const activeVersion = versions?.find(v => v.status === 'active');
      if (!activeVersion) throw new Error('Нет активной версии для копирования');
      
      const activeData = await promptsApi.getVersion(slug!, activeVersion.version);
      return promptsApi.createVersion(slug!, {
        parent_version_id: activeData.id,
        name: activeData.name,
        description: activeData.description,
        template: activeData.template,
      });
    },
    onSuccess: (newVersion) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.versions(slug!) });
      setSelectedVersion(newVersion.version);
      showSuccess(`Создана версия v${newVersion.version} (draft)`);
    },
    onError: (err: Error) => showError(err?.message || 'Ошибка создания версии'),
  });

  // === HANDLERS ===
  const openEditModal = () => {
    setEditForm({
      name: promptMeta?.name || '',
      description: promptMeta?.description || '',
    });
    setShowEditModal(true);
  };

  // === COMPUTED ===
  const isDraft = currentTemplate?.status === 'draft';
  const canCreateVersion = !versions?.some((v: PromptVersionInfo) => v.status === 'draft');

  // === RENDER ===
  if (!slug) {
    return <div className={styles.wrap}>Промпт не найден</div>;
  }

  return (
    <div className={styles.wrap}>
      {/* === HEADER === */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{promptMeta?.name || slug}</h1>
          <p className={styles.subtitle}><code>{slug}</code></p>
        </div>
        <div className={styles.headerActions}>
          <Button variant="outline" onClick={openEditModal}>✏️ Редактировать</Button>
          <Link to="/admin/prompts">
            <Button variant="outline">← Назад</Button>
          </Link>
        </div>
      </div>

      <div className={styles.grid}>
        {/* === ЛЕВАЯ ЧАСТЬ: ПРОМПТ (read-only) === */}
        <div className={styles.card}>
          {/* Атрибуты промпта */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ marginBottom: '12px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Название</span>
              <p style={{ margin: '4px 0 0', fontWeight: 500 }}>{promptMeta?.name || '—'}</p>
            </div>
            
            <div style={{ marginBottom: '12px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Slug</span>
              <p style={{ margin: '4px 0 0' }}><code>{slug}</code></p>
            </div>
            
            <div style={{ marginBottom: '12px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Описание</span>
              <p style={{ margin: '4px 0 0', color: promptMeta?.description ? 'inherit' : 'var(--muted)' }}>
                {promptMeta?.description || 'Нет описания'}
              </p>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Тип</span>
              <p style={{ margin: '4px 0 0' }}>
                <Badge tone="neutral">
                  {TYPE_LABELS[promptMeta?.type || 'prompt'] || promptMeta?.type}
                </Badge>
              </p>
            </div>
          </div>

          {/* Таблица версий (темплейтов) */}
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{ fontSize: '0.875rem', fontWeight: 600, margin: '0 0 8px' }}>Версии</h3>
            {versionsLoading ? (
              <Skeleton height={100} />
            ) : (
              <div style={{ border: '1px solid var(--border)', borderRadius: '4px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-subtle)' }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 500 }}>Версия</th>
                      <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 500 }}>Статус</th>
                      <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 500 }}>Дата</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions?.map((v: PromptVersionInfo) => (
                      <tr
                        key={v.id}
                        onClick={() => setSelectedVersion(v.version)}
                        style={{
                          cursor: 'pointer',
                          background: selectedVersion === v.version ? 'var(--bg-hover)' : 'transparent',
                          borderTop: '1px solid var(--border)',
                        }}
                      >
                        <td style={{ padding: '6px 8px' }}><code>v{v.version}</code></td>
                        <td style={{ padding: '6px 8px' }}>
                          <Badge tone={STATUS_TONES[v.status]}>
                            {STATUS_LABELS[v.status]}
                          </Badge>
                        </td>
                        <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>
                          {new Date(v.created_at).toLocaleDateString('ru-RU')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Агенты */}
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{ fontSize: '0.875rem', fontWeight: 600, margin: '0 0 8px' }}>
              Агенты {agents && agents.length > 0 && `(${agents.length})`}
            </h3>
            {agents && agents.length > 0 ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {agents.map((agent: AgentUsingPrompt) => (
                  <Link key={agent.slug} to={`/admin/agents/${agent.slug}`}>
                    <Badge tone="info">{agent.name}</Badge>
                  </Link>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--muted)', fontSize: '0.8125rem', margin: 0 }}>Нет агентов</p>
            )}
          </div>

          {/* Кнопка создания версии */}
          <div style={{ paddingTop: '12px', borderTop: '1px solid var(--border)' }}>
            <Button
              variant="outline"
              onClick={() => createVersionMutation.mutate()}
              disabled={!canCreateVersion || createVersionMutation.isPending}
              title={!canCreateVersion ? 'Сначала активируйте draft-версию' : ''}
            >
              {createVersionMutation.isPending ? 'Создание...' : '+ Новая версия'}
            </Button>
          </div>
        </div>

        {/* === ПРАВАЯ ЧАСТЬ: ТЕМПЛЕЙТ === */}
        <div className={styles.card}>
          {templateLoading ? (
            <Skeleton height={400} />
          ) : currentTemplate ? (
            <>
              {/* Заголовок */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                <h2 style={{ margin: 0, fontSize: '1.125rem' }}>Версия {currentTemplate.version}</h2>
                <Badge tone={STATUS_TONES[currentTemplate.status]}>
                  {STATUS_LABELS[currentTemplate.status]}
                </Badge>
              </div>

              {/* Темплейт */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '8px' }}>
                  Темплейт (Jinja2)
                </label>
                <Textarea
                  value={editedTemplate}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                    setEditedTemplate(e.target.value);
                    setHasTemplateChanges(true);
                  }}
                  disabled={!isDraft}
                  rows={20}
                  style={{ fontFamily: 'monospace', fontSize: '0.875rem', width: '100%' }}
                />
                {!isDraft && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--muted)', margin: '8px 0 0' }}>
                    Только draft-версии можно редактировать
                  </p>
                )}
              </div>

              {/* Кнопки для draft */}
              {isDraft && (
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button
                    variant="primary"
                    onClick={() => saveTemplateMutation.mutate()}
                    disabled={!hasTemplateChanges || saveTemplateMutation.isPending}
                  >
                    {saveTemplateMutation.isPending ? 'Сохранение...' : 'Сохранить'}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => activateMutation.mutate()}
                    disabled={activateMutation.isPending || hasTemplateChanges}
                    title={hasTemplateChanges ? 'Сначала сохраните изменения' : ''}
                  >
                    {activateMutation.isPending ? 'Активация...' : 'Активировать'}
                  </Button>
                </div>
              )}
            </>
          ) : (
            <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px' }}>
              Выберите версию слева
            </div>
          )}
        </div>
      </div>

      {/* === ИСТОРИЯ ИЗМЕНЕНИЙ === */}
      <div className={styles.card} style={{ marginTop: '1.5rem' }}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>История изменений</h2>
          <p className={styles.cardDescription}>
            Хронология версий и изменений промпта
          </p>
        </div>
        
        <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
          {versions && versions.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {versions.map((v: PromptVersionInfo, index: number) => (
                <div 
                  key={v.id}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '12px',
                    background: index === 0 ? 'var(--bg-hover)' : 'transparent',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                  }}
                >
                  <div style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: v.status === 'active' ? 'var(--success)' : v.status === 'draft' ? 'var(--warning)' : 'var(--muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    flexShrink: 0,
                  }}>
                    v{v.version}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <strong>Версия {v.version}</strong>
                      <Badge tone={STATUS_TONES[v.status]}>{STATUS_LABELS[v.status]}</Badge>
                    </div>
                    <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--muted)' }}>
                      {v.status === 'active' && 'Текущая активная версия • '}
                      {v.status === 'draft' && 'Черновик для редактирования • '}
                      {v.status === 'archived' && 'Архивная версия • '}
                      Создана {new Date(v.created_at).toLocaleString('ru-RU', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '20px' }}>
              Нет истории изменений
            </p>
          )}
        </div>
      </div>

      {/* === МОДАЛКА РЕДАКТИРОВАНИЯ ПРОМПТА === */}
      <Modal
        open={showEditModal}
        onClose={() => setShowEditModal(false)}
        title="Редактировать промпт"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500 }}>Название</label>
            <Input
              value={editForm.name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
                setEditForm({ ...editForm, name: e.target.value })
              }
              placeholder="Название промпта"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500 }}>Описание</label>
            <Textarea
              value={editForm.description}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => 
                setEditForm({ ...editForm, description: e.target.value })
              }
              rows={3}
              placeholder="Описание промпта..."
            />
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--muted)', margin: 0 }}>
            Slug нельзя изменить после создания
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
            <Button variant="outline" onClick={() => setShowEditModal(false)}>Отмена</Button>
            <Button
              variant="primary"
              onClick={() => updatePromptMutation.mutate()}
              disabled={updatePromptMutation.isPending}
            >
              {updatePromptMutation.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default PromptDetailPage;

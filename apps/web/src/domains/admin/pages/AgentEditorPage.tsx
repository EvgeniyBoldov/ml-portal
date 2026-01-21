import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi, promptsApi, toolsApi, collectionsApi, AgentCreate } from '@/shared/api';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

export function AgentEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const isNew = !slug || slug === 'new';

  const [formData, setFormData] = useState<AgentCreate>({
    slug: '',
    name: '',
    description: '',
    system_prompt_slug: '',
    tools: [],
    available_collections: [],
    generation_config: {},
    is_active: true,
    enable_logging: true,
  });

  // Load metadata for selectors
  const { data: prompts } = useQuery({
    queryKey: ['prompts', 'list'],
    queryFn: () => promptsApi.list(),
  });

  const { data: tools } = useQuery({
    queryKey: ['tools', 'list'],
    queryFn: () => toolsApi.list(),
  });

  const { data: collections } = useQuery({
    queryKey: ['collections', 'list'],
    queryFn: () => collectionsApi.list(),
  });

  // Load agent data if editing
  const { data: existingAgent, isLoading } = useQuery({
    queryKey: ['agents', slug],
    queryFn: () => agentsApi.get(slug!),
    enabled: !isNew,
  });

  useEffect(() => {
    if (existingAgent) {
      setFormData({
        slug: existingAgent.slug,
        name: existingAgent.name,
        description: existingAgent.description || '',
        system_prompt_slug: existingAgent.system_prompt_slug,
        tools: existingAgent.tools,
        available_collections: existingAgent.available_collections || [],
        generation_config: existingAgent.generation_config || {},
        is_active: existingAgent.is_active,
        enable_logging: existingAgent.enable_logging,
      });
    }
  }, [existingAgent]);

  const saveMutation = useMutation({
    mutationFn: (data: AgentCreate) => {
        if (isNew) return agentsApi.create(data);
        return agentsApi.update(slug!, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      showSuccess('Agent saved successfully');
      navigate('/admin/agents');
    },
    onError: (err) => {
      showError('Error saving agent');
      console.error(err);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  const toggleTool = (toolSlug: string) => {
    const currentTools = formData.tools;
    if (currentTools.includes(toolSlug)) {
      setFormData({ ...formData, tools: currentTools.filter(t => t !== toolSlug) });
    } else {
      setFormData({ ...formData, tools: [...currentTools, toolSlug] });
    }
  };

  const toggleCollection = (collectionSlug: string) => {
    const currentCollections = formData.available_collections || [];
    if (currentCollections.includes(collectionSlug)) {
      setFormData({ ...formData, available_collections: currentCollections.filter(c => c !== collectionSlug) });
    } else {
      setFormData({ ...formData, available_collections: [...currentCollections, collectionSlug] });
    }
  };

  const hasCollectionSearchTool = formData.tools.includes('collection.search');

  // Load generated prompt for preview
  const { data: generatedPrompt, refetch: refetchPrompt } = useQuery({
    queryKey: ['agents', slug, 'generated-prompt'],
    queryFn: () => agentsApi.getGeneratedPrompt(slug!),
    enabled: !isNew && !!slug,
  });

  // Refetch generated prompt when tools or collections change
  useEffect(() => {
    if (!isNew && slug) {
      refetchPrompt();
    }
  }, [formData.tools, formData.available_collections, isNew, slug, refetchPrompt]);

  if (!isNew && isLoading) {
    return <div className="p-6 text-center text-gray-500">Loading agent...</div>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          {isNew ? 'Создать Агента' : `Редактировать: ${slug}`}
        </h1>
        <Link to="/admin/agents">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <div className={styles.grid}>
        <form id="agent-form" onSubmit={handleSubmit}>
        {/* Main Settings */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Профиль Агента</h2>
            <p className={styles.cardDescription}>
              Базовые настройки идентификации
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Slug (ID)</label>
            <Input 
              value={formData.slug} 
              onChange={e => setFormData({...formData, slug: e.target.value})}
              disabled={!isNew}
              placeholder="network-assistant"
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Название</label>
            <Input 
              value={formData.name} 
              onChange={e => setFormData({...formData, name: e.target.value})}
              placeholder="Network Engineer Helper"
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Описание</label>
            <Textarea 
              value={formData.description} 
              onChange={e => setFormData({...formData, description: e.target.value})}
              rows={3}
            />
          </div>
        </div>

        {/* Configuration */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Конфигурация ("Мозги")</h2>
            <p className={styles.cardDescription}>
              Выбор системного промпта и доступных инструментов
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>System Prompt</label>
            <select 
              className={styles.select}
              value={formData.system_prompt_slug}
              onChange={e => setFormData({...formData, system_prompt_slug: e.target.value})}
              required
            >
              <option value="">Выберите системный промпт...</option>
              {prompts?.map(p => (
                <option key={p.slug} value={p.slug}>
                  {p.name} ({p.slug})
                </option>
              ))}
            </select>
            <p className={styles.description}>
              Определяет личность и базовые инструкции поведения
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Доступные Инструменты</label>
            <div className={styles.toolsList}>
              {tools?.length === 0 && (
                <div className={styles.emptyState}>Нет доступных инструментов</div>
              )}
              {tools?.map(tool => {
                const isSelected = formData.tools.includes(tool.slug);
                return (
                  <div 
                    key={tool.slug} 
                    className={`${styles.toolItem} ${isSelected ? styles.selected : ''}`}
                    onClick={() => toggleTool(tool.slug)}
                  >
                    <input 
                      type="checkbox"
                      className={styles.toolCheckbox}
                      checked={isSelected}
                      onChange={() => toggleTool(tool.slug)}
                      onClick={e => e.stopPropagation()}
                    />
                    <div className={styles.toolInfo}>
                      <div className={styles.toolName}>{tool.name}</div>
                      <div className={styles.toolSlug}>{tool.slug}</div>
                      {tool.description && (
                        <div className={styles.toolDescription}>{tool.description}</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className={styles.description}>
              Выберите функции, которые агент может вызывать
            </p>
          </div>

          {hasCollectionSearchTool && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Доступные Коллекции</label>
              <div className={styles.toolsList}>
                {collections?.length === 0 && (
                  <div className={styles.emptyState}>Нет доступных коллекций</div>
                )}
                {collections?.map(collection => {
                  const isSelected = (formData.available_collections || []).includes(collection.slug);
                  return (
                    <div 
                      key={collection.slug} 
                      className={`${styles.toolItem} ${isSelected ? styles.selected : ''}`}
                      onClick={() => toggleCollection(collection.slug)}
                    >
                      <input 
                        type="checkbox"
                        className={styles.toolCheckbox}
                        checked={isSelected}
                        onChange={() => toggleCollection(collection.slug)}
                        onClick={e => e.stopPropagation()}
                      />
                      <div className={styles.toolInfo}>
                        <div className={styles.toolName}>{collection.name}</div>
                        <div className={styles.toolSlug}>{collection.slug}</div>
                        {collection.description && (
                          <div className={styles.toolDescription}>{collection.description}</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className={styles.description}>
                Выберите коллекции, к которым агент будет иметь доступ при использовании collection.search
              </p>
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.label}>Настройки логирования</label>
            <div className={styles.toolsList} style={{ maxHeight: 'auto', padding: '12px' }}>
              <div 
                className={`${styles.toolItem} ${formData.enable_logging ? styles.selected : ''}`}
                onClick={() => setFormData({ ...formData, enable_logging: !formData.enable_logging })}
              >
                <input 
                  type="checkbox"
                  className={styles.toolCheckbox}
                  checked={formData.enable_logging ?? true}
                  onChange={() => setFormData({ ...formData, enable_logging: !formData.enable_logging })}
                  onClick={e => e.stopPropagation()}
                />
                <div className={styles.toolInfo}>
                  <div className={styles.toolName}>Логировать выполнение</div>
                  <div className={styles.toolDescription}>
                    Сохранять детальную информацию о каждом запуске агента (шаги, tool calls, результаты)
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className={styles.actions}>
             <Button 
              type="submit" 
              variant="primary" 
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        </div>
      </form>

      {/* Generated Prompt Preview */}
      {!isNew && generatedPrompt && (
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Сгенерированный Промпт</h2>
            <p className={styles.cardDescription}>
              Финальный промпт, который видит LLM (базовый промпт + инструменты + коллекции)
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Базовый промпт</label>
            <div className={styles.promptPreview}>
              <pre>{generatedPrompt.base_prompt}</pre>
            </div>
            <p className={styles.description}>
              Источник: {generatedPrompt.base_prompt_slug}
            </p>
          </div>

          {generatedPrompt.tools_section && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Секция инструментов</label>
              <div className={styles.promptPreview}>
                <pre>{generatedPrompt.tools_section}</pre>
              </div>
            </div>
          )}

          {generatedPrompt.collections_section && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Секция коллекций</label>
              <div className={styles.promptPreview}>
                <pre>{generatedPrompt.collections_section}</pre>
              </div>
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.label}>Финальный промпт</label>
            <div className={styles.promptPreview} style={{ maxHeight: '400px', overflow: 'auto' }}>
              <pre>{generatedPrompt.final_prompt}</pre>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

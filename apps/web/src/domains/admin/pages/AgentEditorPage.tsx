import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi, promptsApi, toolsApi, collectionsApi, AgentCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import Badge from '@/shared/ui/Badge';
import Modal from '@/shared/ui/Modal';
import { Tabs, TabPanel } from '@/shared/ui/Tabs';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './AgentEditorPage.module.css';

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

  // Modal state for prompt preview
  const [showPromptModal, setShowPromptModal] = useState(false);
  const [promptTab, setPromptTab] = useState<'base' | 'generated'>('base');

  // Load generated prompt for preview (only when modal is open)
  const { data: generatedPrompt } = useQuery({
    queryKey: qk.agents.detail(slug || ''),
    queryFn: () => agentsApi.getGeneratedPrompt(slug!),
    enabled: !isNew && !!slug && showPromptModal,
  });

  // Get selected prompt info
  const selectedPrompt = prompts?.find(p => p.slug === formData.system_prompt_slug);

  if (!isNew && isLoading) {
    return <div className={styles.emptyState}>Загрузка агента...</div>;
  }

  return (
    <div className={styles.wrap}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>
            {isNew ? 'Создать Агента' : formData.name || slug}
          </h1>
          {!isNew && <p className={styles.subtitle}><code>{slug}</code></p>}
        </div>
        <div className={styles.headerActions}>
          <Link to="/admin/agents">
            <Button variant="outline">← Назад</Button>
          </Link>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className={styles.content}>
          {/* Basic Info Card */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Основная информация</h2>
            </div>

            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Slug (ID)</label>
                <Input 
                  value={formData.slug} 
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({...formData, slug: e.target.value})}
                  disabled={!isNew}
                  placeholder="network-assistant"
                  required
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Название</label>
                <Input 
                  value={formData.name} 
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({...formData, name: e.target.value})}
                  placeholder="Network Engineer Helper"
                  required
                />
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>Описание</label>
              <Textarea 
                value={formData.description} 
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setFormData({...formData, description: e.target.value})}
                rows={2}
                placeholder="Краткое описание агента..."
              />
            </div>
          </div>

          {/* System Prompt Card */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Системный промпт</h2>
              <p className={styles.cardDescription}>Определяет личность и инструкции поведения</p>
            </div>

            <div className={styles.formGroup}>
              <div className={styles.promptSelector}>
                <select 
                  className={styles.select}
                  value={formData.system_prompt_slug}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFormData({...formData, system_prompt_slug: e.target.value})}
                  required
                >
                  <option value="">Выберите промпт...</option>
                  {prompts?.map((p: { slug: string; name: string }) => (
                    <option key={p.slug} value={p.slug}>{p.name}</option>
                  ))}
                </select>
                {formData.system_prompt_slug && !isNew && (
                  <Button 
                    type="button" 
                    variant="outline" 
                    onClick={() => setShowPromptModal(true)}
                  >
                    Превью
                  </Button>
                )}
              </div>
              {selectedPrompt && (
                <div className={styles.promptInfo}>
                  <Badge tone="info">{selectedPrompt.slug}</Badge>
                  <Link to={`/admin/prompts/${selectedPrompt.slug}`}>
                    <Button variant="link" size="small">Открыть →</Button>
                  </Link>
                </div>
              )}
            </div>
          </div>

          {/* Tools Card */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Инструменты</h2>
              <p className={styles.cardDescription}>
                Выбрано: {formData.tools.length} из {tools?.length || 0}
              </p>
            </div>

            <div className={styles.toolsGrid}>
              {tools?.length === 0 && (
                <div className={styles.emptyState}>Нет доступных инструментов</div>
              )}
              {tools?.map((tool: { slug: string; name: string }) => {
                const isSelected = formData.tools.includes(tool.slug);
                return (
                  <div 
                    key={tool.slug} 
                    className={`${styles.toolChip} ${isSelected ? styles.selected : ''}`}
                    onClick={() => toggleTool(tool.slug)}
                  >
                    <input 
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleTool(tool.slug)}
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                    />
                    <div className={styles.toolChipInfo}>
                      <div className={styles.toolChipName}>{tool.name}</div>
                      <div className={styles.toolChipSlug}>{tool.slug}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Collections Card (only if collection.search tool selected) */}
          {hasCollectionSearchTool && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <h2 className={styles.cardTitle}>Коллекции</h2>
                <p className={styles.cardDescription}>
                  Доступ для collection.search
                </p>
              </div>

              <div className={styles.collectionsGrid}>
                {collections?.items?.length === 0 && (
                  <div className={styles.emptyState}>Нет доступных коллекций</div>
                )}
                {collections?.items?.map((collection: { slug: string; name: string }) => {
                  const isSelected = (formData.available_collections || []).includes(collection.slug);
                  return (
                    <div 
                      key={collection.slug} 
                      className={`${styles.toolChip} ${isSelected ? styles.selected : ''}`}
                      onClick={() => toggleCollection(collection.slug)}
                    >
                      <input 
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleCollection(collection.slug)}
                        onClick={(e: React.MouseEvent) => e.stopPropagation()}
                      />
                      <div className={styles.toolChipInfo}>
                        <div className={styles.toolChipName}>{collection.name}</div>
                        <div className={styles.toolChipSlug}>{collection.slug}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Options Card */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Настройки</h2>
            </div>

            <div className={styles.optionsRow}>
              <div 
                className={`${styles.optionItem} ${formData.is_active ? styles.active : ''}`}
                onClick={() => setFormData({ ...formData, is_active: !formData.is_active })}
              >
                <input 
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={() => setFormData({ ...formData, is_active: !formData.is_active })}
                />
                <span>Активен</span>
              </div>
              <div 
                className={`${styles.optionItem} ${formData.enable_logging ? styles.active : ''}`}
                onClick={() => setFormData({ ...formData, enable_logging: !formData.enable_logging })}
              >
                <input 
                  type="checkbox"
                  checked={formData.enable_logging ?? true}
                  onChange={() => setFormData({ ...formData, enable_logging: !formData.enable_logging })}
                />
                <span>Логирование</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className={styles.actions}>
            <Link to="/admin/agents">
              <Button type="button" variant="outline">Отмена</Button>
            </Link>
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

      {/* Prompt Preview Modal */}
      <Modal 
        open={showPromptModal} 
        onClose={() => setShowPromptModal(false)} 
        title="Превью промпта"
        size="lg"
      >
        <Tabs
          tabs={[
            { id: 'base', label: 'Базовый' },
            { id: 'generated', label: 'Сгенерированный' },
          ]}
          activeTab={promptTab}
          onChange={(tab) => setPromptTab(tab as 'base' | 'generated')}
        >
          <TabPanel id="base" activeTab={promptTab}>
            <div className={styles.promptPreview}>
              <pre>{generatedPrompt?.base_prompt || 'Загрузка...'}</pre>
            </div>
          </TabPanel>

          <TabPanel id="generated" activeTab={promptTab}>
            {generatedPrompt ? (
              <div className={styles.promptPreview}>
                <pre>{generatedPrompt.final_prompt}</pre>
              </div>
            ) : (
              <div className={styles.emptyState}>Загрузка...</div>
            )}
          </TabPanel>
        </Tabs>
      </Modal>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentsApi, promptsApi, toolsApi, AgentCreate } from '@/shared/api';
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
    generation_config: {},
    is_active: true
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
        generation_config: existingAgent.generation_config || {},
        is_active: existingAgent.is_active
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

      <form id="agent-form" onSubmit={handleSubmit} className={styles.grid}>
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
            <div className="border rounded-md p-4 bg-gray-50 max-h-[300px] overflow-y-auto">
              {tools?.length === 0 && <div className="text-sm text-gray-500">Нет доступных инструментов</div>}
              {tools?.map(tool => (
                <div key={tool.slug} className="flex items-start gap-2 mb-2 last:mb-0">
                  <input 
                    type="checkbox"
                    id={`tool-${tool.slug}`}
                    checked={formData.tools.includes(tool.slug)}
                    onChange={() => toggleTool(tool.slug)}
                    className="mt-1"
                  />
                  <label htmlFor={`tool-${tool.slug}`} className="cursor-pointer">
                    <div className="text-sm font-medium text-gray-900">{tool.name}</div>
                    <div className="text-xs text-gray-500 font-mono">{tool.slug}</div>
                  </label>
                </div>
              ))}
            </div>
            <p className={styles.description}>
              Выберите функции, которые агент может вызывать
            </p>
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
    </div>
  );
}

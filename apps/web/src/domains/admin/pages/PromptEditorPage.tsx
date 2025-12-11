import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { promptsApi, PromptCreate } from '@/shared/api';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

// --- Constants & Helpers ---

const PROMPT_TYPES = [
  { value: 'chat', label: 'Chat (System)', description: 'Обычный системный промпт' },
  { value: 'rag', label: 'RAG System', description: 'Промпт с контекстом из базы знаний' },
  { value: 'agent', label: 'Agent', description: 'Инструкции для агента с инструментами' },
  { value: 'task', label: 'Task / Classification', description: 'Для конкретных задач (суммаризация, классификация)' },
];

const SAMPLE_CONTEXTS: Record<string, { variables: object, description: string, doc: string[] }> = {
  chat: {
    variables: {
      name: "User",
      history: [
        { role: "user", content: "Привет!" },
        { role: "assistant", content: "Привет! Чем могу помочь?" }
      ]
    },
    description: "Базовый контекст чата",
    doc: ["name (str) - Имя пользователя", "history (list) - История сообщений"]
  },
  rag: {
    variables: {
      query: "Как настроить VPN?",
      results: [
        { 
          text: "Для настройки VPN перейдите в раздел Сеть...", 
          source_id: "manual_v2.pdf", 
          page: 12,
          score: 0.89
        },
        { 
          text: "VPN-клиент можно скачать по ссылке...", 
          source_id: "wiki_page_123", 
          page: null,
          score: 0.75
        }
      ],
      history: []
    },
    description: "RAG: Вопрос + Найденные документы",
    doc: [
      "query (str) - Вопрос пользователя",
      "results (list) - Список найденных чанков",
      "results[].text (str) - Текст документа",
      "results[].source_id (str) - Источник",
      "results[].page (int) - Номер страницы (опционально)"
    ]
  },
  agent: {
    variables: {
      query: "Проверь статус сервера api-prod",
      tools: [
        { name: "check_status", description: "Проверяет статус сервиса" },
        { name: "restart_service", description: "Перезагружает сервис" }
      ],
      agent_scratchpad: "Thought: Нужно проверить статус...\nAction: check_status..."
    },
    description: "Агент с доступом к инструментам",
    doc: [
      "tools (list) - Доступные функции",
      "agent_scratchpad (str) - История размышлений агента"
    ]
  }
};

export function PromptEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const isNew = !slug || slug === 'new';

  const [formData, setFormData] = useState<PromptCreate>({
    slug: '',
    name: '',
    description: '',
    template: '',
    type: 'chat',
    input_variables: [],
    generation_config: {}
  });

  // Load data if editing
  const { data: existingPrompt, isLoading } = useQuery({
    queryKey: ['prompts', slug],
    queryFn: () => promptsApi.get(slug!),
    enabled: !isNew,
  });

  useEffect(() => {
    if (existingPrompt) {
      setFormData({
        slug: existingPrompt.slug,
        name: existingPrompt.name,
        description: existingPrompt.description || '',
        template: existingPrompt.template,
        type: existingPrompt.type,
        input_variables: existingPrompt.input_variables || [],
        generation_config: existingPrompt.generation_config || {}
      });
    }
  }, [existingPrompt]);

  const saveMutation = useMutation({
    mutationFn: (data: PromptCreate) => promptsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
      showSuccess('Prompt saved successfully');
      navigate('/admin/prompts');
    },
    onError: (err) => {
      showError('Error saving prompt');
      console.error(err);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  // Playground state
  const [testVariables, setTestVariables] = useState('{}');
  const [previewResult, setPreviewResult] = useState<string | null>(null);
  
  // Auto-fill example when type changes (only if empty)
  useEffect(() => {
    if (testVariables === '{}' || testVariables === '') {
      // Try to find context by exact type match or generic 'chat'
      const contextKey = SAMPLE_CONTEXTS[formData.type] ? formData.type : 'chat';
      const example = SAMPLE_CONTEXTS[contextKey]?.variables || {};
      setTestVariables(JSON.stringify(example, null, 2));
    }
  }, [formData.type]);

  const loadExample = () => {
    const contextKey = SAMPLE_CONTEXTS[formData.type] ? formData.type : 'chat';
    const example = SAMPLE_CONTEXTS[contextKey]?.variables || {};
    setTestVariables(JSON.stringify(example, null, 2));
  };
  
  const previewMutation = useMutation({
    mutationFn: async () => {
      try {
        const vars = JSON.parse(testVariables);
        const res = await promptsApi.preview(formData.template, vars);
        return res.rendered;
      } catch (e: any) {
        throw new Error('Invalid JSON variables or template error: ' + (e.message || e));
      }
    },
    onSuccess: (data) => setPreviewResult(data),
    onError: (err: any) => setPreviewResult(`Error: ${err.message}`)
  });

  // Helper docs
  const currentDocs = SAMPLE_CONTEXTS[formData.type]?.doc || SAMPLE_CONTEXTS['chat'].doc;

  if (!isNew && isLoading) {
    return <div className="p-6 text-center text-gray-500">Loading prompt...</div>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          {isNew ? 'Создать Промпт' : `Редактировать: ${slug}`}
        </h1>
        <Link to="/admin/prompts">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <div className={styles.grid}>
        {/* Editor Column */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Настройки</h2>
            <p className={styles.cardDescription}>
              Основные параметры промпта и шаблон Jinja2
            </p>
          </div>

          <form id="prompt-form" onSubmit={handleSubmit} className="space-y-4">
            <div className={styles.formGroup}>
              <label className={styles.label}>Slug (ID)</label>
              <Input 
                value={formData.slug} 
                onChange={e => setFormData({...formData, slug: e.target.value})}
                disabled={!isNew}
                placeholder="chat.rag.system"
                required
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>Название</label>
              <Input 
                value={formData.name} 
                onChange={e => setFormData({...formData, name: e.target.value})}
                placeholder="System Prompt for RAG"
                required
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>Тип</label>
              <select 
                className={styles.select}
                value={formData.type}
                onChange={e => setFormData({...formData, type: e.target.value})}
              >
                {PROMPT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <p className={styles.description}>
                {PROMPT_TYPES.find(t => t.value === formData.type)?.description}
              </p>
            </div>
            
            <div className={styles.formGroup}>
               <div className="flex justify-between items-center mb-1">
                 <label className={styles.label}>Template (Jinja2)</label>
                 <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">
                   {formData.type.toUpperCase()} MODE
                 </span>
               </div>
               <Textarea 
                 className={styles.editor}
                 value={formData.template}
                 onChange={e => setFormData({...formData, template: e.target.value})}
                 required
               />
               {/* Variable Hints */}
               <div className="mt-2 p-3 bg-gray-50 rounded border border-gray-100">
                 <p className="text-xs font-semibold text-gray-500 mb-1">Доступные переменные для {formData.type}:</p>
                 <ul className="text-xs text-gray-600 space-y-0.5 font-mono">
                   {currentDocs.map((doc, i) => (
                     <li key={i}>• {doc}</li>
                   ))}
                 </ul>
               </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>Описание (для админки)</label>
              <Textarea 
                value={formData.description} 
                onChange={e => setFormData({...formData, description: e.target.value})}
                rows={2}
              />
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
          </form>
        </div>

        {/* Playground Column */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Playground</h2>
            <p className={styles.cardDescription}>
              Тестирование рендеринга шаблона с переменными
            </p>
          </div>

          <div className={styles.formGroup}>
            <div className="flex justify-between items-center mb-1">
              <label className={styles.label}>Variables (JSON)</label>
              <button 
                type="button"
                onClick={loadExample}
                className="text-xs text-primary hover:underline"
              >
                Загрузить пример для {formData.type}
              </button>
            </div>
            <Textarea 
              className={styles.editor}
              style={{ minHeight: '200px' }}
              value={testVariables}
              onChange={e => setTestVariables(e.target.value)}
              placeholder='{"name": "User", "context": "..."}'
            />
          </div>

          <div className={styles.actions}>
             <Button 
              onClick={() => previewMutation.mutate()} 
              variant="outline"
              disabled={previewMutation.isPending}
            >
              {previewMutation.isPending ? 'Рендеринг...' : 'Тест Рендер'}
            </Button>
          </div>

          {previewResult && (
            <div className="mt-4">
               <h3 className={styles.previewTitle}>Результат (Rendered):</h3>
               <div className={previewResult.startsWith('Error:') ? styles.previewError : styles.preview}>
                 {previewResult}
               </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

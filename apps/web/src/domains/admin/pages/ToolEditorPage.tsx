import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolsApi, ToolCreate } from '@/shared/api';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
// Reuse styles from prompt editor
import styles from './PromptEditorPage.module.css';

const TOOL_TYPES = [
  { value: 'api', label: 'REST API', description: 'HTTP call to external service' },
  { value: 'function', label: 'Python Function', description: 'Internal Python function call' },
  { value: 'database', label: 'Database Query', description: 'SQL/Vector DB Query' },
];

const DEFAULT_INPUT_SCHEMA = {
  type: "object",
  properties: {
    query: { type: "string", description: "Search query" }
  },
  required: ["query"]
};

export function ToolEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const isNew = !slug || slug === 'new';

  const [formData, setFormData] = useState<ToolCreate>({
    slug: '',
    name: '',
    description: '',
    type: 'api',
    input_schema: DEFAULT_INPUT_SCHEMA,
    output_schema: {},
    config: {},
    is_active: true
  });

  // Text state for JSON editors
  const [inputSchemaText, setInputSchemaText] = useState(JSON.stringify(DEFAULT_INPUT_SCHEMA, null, 2));
  const [outputSchemaText, setOutputSchemaText] = useState('{}');
  const [configText, setConfigText] = useState('{}');

  // Load data if editing
  const { data: existingTool, isLoading } = useQuery({
    queryKey: ['tools', slug],
    queryFn: () => toolsApi.get(slug!),
    enabled: !isNew,
  });

  useEffect(() => {
    if (existingTool) {
      setFormData({
        slug: existingTool.slug,
        name: existingTool.name,
        description: existingTool.description || '',
        type: existingTool.type,
        input_schema: existingTool.input_schema,
        output_schema: existingTool.output_schema || {},
        config: existingTool.config || {},
        is_active: existingTool.is_active
      });
      setInputSchemaText(JSON.stringify(existingTool.input_schema, null, 2));
      setOutputSchemaText(JSON.stringify(existingTool.output_schema || {}, null, 2));
      setConfigText(JSON.stringify(existingTool.config || {}, null, 2));
    }
  }, [existingTool]);

  const saveMutation = useMutation({
    mutationFn: (data: ToolCreate) => {
        if (isNew) return toolsApi.create(data);
        return toolsApi.update(slug!, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] });
      showSuccess('Tool saved successfully');
      navigate('/admin/tools');
    },
    onError: (err) => {
      showError('Error saving tool');
      console.error(err);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const inputSchema = JSON.parse(inputSchemaText);
      const outputSchema = JSON.parse(outputSchemaText);
      const config = JSON.parse(configText);
      
      saveMutation.mutate({
        ...formData,
        input_schema: inputSchema,
        output_schema: outputSchema,
        config: config
      });
    } catch (err) {
      showError('Invalid JSON in one of the fields');
    }
  };

  if (!isNew && isLoading) {
    return <div className="p-6 text-center text-gray-500">Loading tool...</div>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          {isNew ? 'Создать Инструмент' : `Редактировать: ${slug}`}
        </h1>
        <Link to="/admin/tools">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <form id="tool-form" onSubmit={handleSubmit} className={styles.grid}>
        {/* Main Settings */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Основные настройки</h2>
            <p className={styles.cardDescription}>
              Идентификация и тип инструмента
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Slug (ID)</label>
            <Input 
              value={formData.slug} 
              onChange={e => setFormData({...formData, slug: e.target.value})}
              disabled={!isNew}
              placeholder="netbox.get_device"
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Название</label>
            <Input 
              value={formData.name} 
              onChange={e => setFormData({...formData, name: e.target.value})}
              placeholder="Get Device Info"
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
              {TOOL_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p className={styles.description}>
              {TOOL_TYPES.find(t => t.value === formData.type)?.description}
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Описание (для LLM)</label>
            <Textarea 
              value={formData.description} 
              onChange={e => setFormData({...formData, description: e.target.value})}
              rows={3}
              placeholder="Describes what this tool does..."
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Конфигурация (JSON)</label>
            <Textarea 
              className={styles.editor}
              style={{ minHeight: '150px' }}
              value={configText}
              onChange={e => setConfigText(e.target.value)}
              placeholder='{"url": "https://api.netbox...", "method": "GET"}'
            />
          </div>
        </div>

        {/* Schemas */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Схемы Данных</h2>
            <p className={styles.cardDescription}>
              JSON Schema для входа и выхода
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Input Schema (Arguments)</label>
            <p className={styles.description}>Структура аргументов, которые генерирует LLM</p>
            <Textarea 
              className={styles.editor}
              style={{ minHeight: '200px' }}
              value={inputSchemaText}
              onChange={e => setInputSchemaText(e.target.value)}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Output Schema (Result)</label>
            <p className={styles.description}>Ожидаемая структура ответа инструмента</p>
            <Textarea 
              className={styles.editor}
              style={{ minHeight: '200px' }}
              value={outputSchemaText}
              onChange={e => setOutputSchemaText(e.target.value)}
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
        </div>
      </form>
    </div>
  );
}

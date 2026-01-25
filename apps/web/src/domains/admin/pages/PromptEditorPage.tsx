/**
 * PromptEditorPage - Создание нового промпта
 * 
 * При создании указываем:
 * - Slug (обязательно, нельзя изменить после создания)
 * - Название
 * - Описание
 * - Тип (prompt/baseline)
 * - Темплейт (v1, draft)
 */
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { promptsApi } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

import styles from './PromptEditorPage.module.css';

// Типы промптов
const PROMPT_TYPES = [
  { value: 'prompt', label: 'Промпт' },
  { value: 'baseline', label: 'Baseline' },
];

export function PromptEditorPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    type: 'prompt',
    template: '',
  });

  const saveMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      // Создаём первую версию промпта (version=1, status=draft)
      return promptsApi.create({
        slug: data.slug,
        name: data.name,
        description: data.description,
        template: data.template,
        type: data.type as 'prompt' | 'baseline',
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
      showSuccess('Промпт создан');
      navigate(`/admin/prompts/${data.slug}`);
    },
    onError: (err: any) => {
      showError(err?.message || 'Ошибка при создании промпта');
      console.error(err);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Создать Промпт</h1>
          <p className={styles.subtitle}>Версия 1 будет создана автоматически со статусом draft</p>
        </div>
        <Link to="/admin/prompts">
          <Button variant="outline">← Назад</Button>
        </Link>
      </div>

      <form onSubmit={handleSubmit}>
        <div className={styles.card}>
          <div className={styles.formGroup}>
            <label className={styles.label}>Slug (ID)</label>
            <Input 
              value={formData.slug} 
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({...formData, slug: e.target.value})}
              placeholder="agent.rag.system"
              required
            />
            <p className={styles.description}>
              Уникальный идентификатор промпта (нельзя изменить после создания)
            </p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Название</label>
            <Input 
              value={formData.name} 
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({...formData, name: e.target.value})}
              placeholder="RAG Agent System Prompt"
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Описание</label>
            <Textarea 
              value={formData.description} 
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setFormData({...formData, description: e.target.value})}
              rows={2}
              placeholder="Краткое описание назначения промпта..."
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Тип</label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({...formData, type: e.target.value})}
              className={styles.select}
              style={{ 
                padding: '8px 12px', 
                borderRadius: '4px', 
                border: '1px solid var(--border)',
                background: 'var(--bg-input)',
                color: 'inherit',
                fontSize: '0.875rem',
              }}
            >
              {PROMPT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          
          <div className={styles.formGroup}>
            <label className={styles.label}>Темплейт (Jinja2)</label>
            <Textarea 
              className={styles.editor}
              value={formData.template}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setFormData({...formData, template: e.target.value})}
              rows={15}
              placeholder="Ты — AI-ассистент с доступом к базе знаний компании..."
              required
            />
            <p className={styles.description}>
              Шаблон промпта с поддержкой Jinja2 синтаксиса
            </p>
          </div>

          <div className={styles.actions}>
            <Link to="/admin/prompts">
              <Button type="button" variant="outline">Отмена</Button>
            </Link>
            <Button 
              type="submit" 
              variant="primary" 
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Создание...' : 'Создать промпт'}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

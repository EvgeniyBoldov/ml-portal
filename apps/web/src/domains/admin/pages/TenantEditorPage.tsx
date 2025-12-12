/**
 * TenantEditorPage - Create/edit tenant with clean UI
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTenant, useModels } from '@shared/api/hooks/useAdmin';
import { tenantApi } from '@shared/api/tenant';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Textarea from '@shared/ui/Textarea';
import { Icon } from '@shared/ui/Icon';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { Skeleton } from '@shared/ui/Skeleton';
import styles from './TenantEditorPage.module.css';

interface FormData {
  name: string;
  description: string;
  is_active: boolean;
  extra_embed_model: string;
  ocr: boolean;
  layout: boolean;
}

export function TenantEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditing = !!id;
  const { data: tenantData, isLoading } = useTenant(id);
  const { data: modelsData } = useModels({ size: 100 });

  const [formData, setFormData] = useState<FormData>({
    name: '',
    description: '',
    is_active: true,
    extra_embed_model: '',
    ocr: false,
    layout: false,
  });
  const [saving, setSaving] = useState(false);

  // Get available embedding models
  const models = modelsData?.items || [];
  const textModels = models.filter(
    m => m.modality === 'text' && (m.state === 'active' || m.state === 'archived')
  );
  const globalEmbed = textModels.find(m => (m as any).global === true);
  const extraModels = textModels.filter(m => !(m as any).global);

  useEffect(() => {
    if (tenantData) {
      setFormData({
        name: tenantData.name || '',
        description: tenantData.description || '',
        is_active: tenantData.is_active ?? true,
        extra_embed_model: (tenantData as any).extra_embed_model || '',
        ocr: tenantData.ocr || false,
        layout: tenantData.layout || false,
      });
    }
  }, [tenantData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      showError('Название обязательно');
      return;
    }

    setSaving(true);
    try {
      if (isEditing) {
        await tenantApi.updateTenant(id!, {
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || null,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Тенант обновлён');
      } else {
        await tenantApi.createTenant({
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || undefined,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Тенант создан');
      }
      navigate('/admin/tenants');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  if (isEditing && isLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.container}>
          <Skeleton height={400} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <button className={styles.backBtn} onClick={() => navigate('/admin/tenants')}>
            <Icon name="arrow-left" size={20} />
          </button>
          <div className={styles.headerTitle}>
            <h1>{isEditing ? 'Редактирование тенанта' : 'Новый тенант'}</h1>
            {isEditing && tenantData && (
              <span className={styles.headerSubtitle}>{tenantData.name}</span>
            )}
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <Icon name="info" size={20} />
              <h2>Основная информация</h2>
            </div>
            <div className={styles.cardBody}>
              <div className={styles.field}>
                <label className={styles.label}>
                  Название <span className={styles.required}>*</span>
                </label>
                <Input
                  value={formData.name}
                  onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Введите название тенанта"
                />
              </div>

              <div className={styles.field}>
                <label className={styles.label}>Описание</label>
                <Textarea
                  value={formData.description}
                  onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Краткое описание тенанта"
                  rows={3}
                />
              </div>

              <div className={styles.switchField}>
                <div className={styles.switchInfo}>
                  <span className={styles.switchLabel}>Активен</span>
                  <span className={styles.switchDesc}>Тенант доступен для использования</span>
                </div>
                <label className={styles.switch}>
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={e => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
                  />
                  <span className={styles.slider} />
                </label>
              </div>
            </div>
          </div>

          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <Icon name="cpu" size={20} />
              <h2>Модели эмбеддинга</h2>
            </div>
            <div className={styles.cardBody}>
              {globalEmbed && (
                <div className={styles.modelInfo}>
                  <div className={styles.modelBadge}>
                    <Icon name="check" size={14} />
                    <span>Глобальная модель</span>
                  </div>
                  <span className={styles.modelName}>{globalEmbed.model}</span>
                  <span className={styles.modelHint}>Применяется автоматически ко всем документам</span>
                </div>
              )}

              <div className={styles.field}>
                <label className={styles.label}>Дополнительная модель</label>
                <select
                  className={styles.select}
                  value={formData.extra_embed_model}
                  onChange={e => setFormData(prev => ({ ...prev, extra_embed_model: e.target.value }))}
                >
                  <option value="">Не использовать</option>
                  {extraModels.map(model => (
                    <option key={model.model} value={model.model}>
                      {model.model} {model.state === 'archived' ? '(архив)' : ''}
                    </option>
                  ))}
                </select>
                <span className={styles.fieldHint}>
                  Документы будут индексироваться дополнительно этой моделью
                </span>
              </div>
            </div>
          </div>

          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <Icon name="settings" size={20} />
              <h2>Настройки обработки</h2>
            </div>
            <div className={styles.cardBody}>
              <div className={styles.switchField}>
                <div className={styles.switchInfo}>
                  <span className={styles.switchLabel}>OCR</span>
                  <span className={styles.switchDesc}>Распознавание текста на изображениях</span>
                </div>
                <label className={styles.switch}>
                  <input
                    type="checkbox"
                    checked={formData.ocr}
                    onChange={e => setFormData(prev => ({ ...prev, ocr: e.target.checked }))}
                  />
                  <span className={styles.slider} />
                </label>
              </div>

              <div className={styles.switchField}>
                <div className={styles.switchInfo}>
                  <span className={styles.switchLabel}>Layout Analysis</span>
                  <span className={styles.switchDesc}>Анализ структуры документа</span>
                </div>
                <label className={styles.switch}>
                  <input
                    type="checkbox"
                    checked={formData.layout}
                    onChange={e => setFormData(prev => ({ ...prev, layout: e.target.checked }))}
                  />
                  <span className={styles.slider} />
                </label>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className={styles.actions}>
            <Button
              type="button"
              variant="secondary"
              onClick={() => navigate('/admin/tenants')}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Сохранение...' : isEditing ? 'Сохранить' : 'Создать'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default TenantEditorPage;

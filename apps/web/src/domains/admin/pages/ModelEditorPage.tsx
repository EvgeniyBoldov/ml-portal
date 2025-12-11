import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi, type Model, type ModelCreate, type ModelUpdate, type ModelType, type ModelStatus } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './ModelEditorPage.module.css';

const MODEL_TYPES: { value: ModelType; label: string }[] = [
  { value: 'llm_chat', label: 'LLM Chat' },
  { value: 'embedding', label: 'Embedding' },
];

const MODEL_STATUSES: { value: ModelStatus; label: string }[] = [
  { value: 'available', label: 'Available' },
  { value: 'unavailable', label: 'Unavailable' },
  { value: 'deprecated', label: 'Deprecated' },
  { value: 'maintenance', label: 'Maintenance' },
];

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'groq', label: 'Groq' },
  { value: 'local', label: 'Local Container' },
  { value: 'azure', label: 'Azure OpenAI' },
];

export function ModelEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const isNew = id === 'new';
  
  // Form state
  const [formData, setFormData] = useState<Partial<ModelCreate>>({
    alias: '',
    name: '',
    type: 'llm_chat',
    provider: 'openai',
    provider_model_name: '',
    base_url: '',
    api_key_ref: '',
    status: 'available',
    enabled: true,
    default_for_type: false,
    model_version: '',
    description: '',
    extra_config: {},
  });
  
  // Extra config for embedding models
  const [vectorDim, setVectorDim] = useState<string>('');
  
  // Load existing model
  const { data: model, isLoading } = useQuery({
    queryKey: qk.admin.models.detail(id || ''),
    queryFn: () => adminApi.getModel(id!),
    enabled: !isNew && !!id,
  });
  
  // Populate form when model loads
  useEffect(() => {
    if (model) {
      setFormData({
        alias: model.alias,
        name: model.name,
        type: model.type,
        provider: model.provider,
        provider_model_name: model.provider_model_name,
        base_url: model.base_url,
        api_key_ref: model.api_key_ref || '',
        status: model.status,
        enabled: model.enabled,
        default_for_type: model.default_for_type,
        model_version: model.model_version || '',
        description: model.description || '',
        extra_config: model.extra_config || {},
      });
      if (model.extra_config?.vector_dim) {
        setVectorDim(String(model.extra_config.vector_dim));
      }
    }
  }, [model]);
  
  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: ModelCreate) => adminApi.createModel(data),
    onSuccess: () => {
      showSuccess('Model created successfully');
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
      navigate('/admin/models');
    },
    onError: (error: Error) => {
      showError(error.message || 'Failed to create model');
    },
  });
  
  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: ModelUpdate) => adminApi.updateModel(id!, data),
    onSuccess: () => {
      showSuccess('Model updated successfully');
      queryClient.invalidateQueries({ queryKey: qk.admin.models.all() });
      queryClient.invalidateQueries({ queryKey: qk.admin.models.detail(id!) });
      navigate('/admin/models');
    },
    onError: (error: Error) => {
      showError(error.message || 'Failed to update model');
    },
  });
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // Build extra_config
    const extra_config: Record<string, unknown> = { ...formData.extra_config };
    if (formData.type === 'embedding' && vectorDim) {
      extra_config.vector_dim = parseInt(vectorDim, 10);
    }
    
    const data = {
      ...formData,
      extra_config: Object.keys(extra_config).length > 0 ? extra_config : undefined,
    } as ModelCreate;
    
    if (isNew) {
      createMutation.mutate(data);
    } else {
      // For update, only send changed fields
      const updateData: ModelUpdate = {};
      if (formData.name !== model?.name) updateData.name = formData.name;
      if (formData.provider !== model?.provider) updateData.provider = formData.provider;
      if (formData.provider_model_name !== model?.provider_model_name) updateData.provider_model_name = formData.provider_model_name;
      if (formData.base_url !== model?.base_url) updateData.base_url = formData.base_url;
      if (formData.api_key_ref !== model?.api_key_ref) updateData.api_key_ref = formData.api_key_ref;
      if (formData.status !== model?.status) updateData.status = formData.status;
      if (formData.enabled !== model?.enabled) updateData.enabled = formData.enabled;
      if (formData.default_for_type !== model?.default_for_type) updateData.default_for_type = formData.default_for_type;
      if (formData.model_version !== model?.model_version) updateData.model_version = formData.model_version;
      if (formData.description !== model?.description) updateData.description = formData.description;
      
      // Always include extra_config if embedding
      if (formData.type === 'embedding') {
        updateData.extra_config = extra_config;
      }
      
      updateMutation.mutate(updateData);
    }
  };
  
  const updateField = <K extends keyof ModelCreate>(field: K, value: ModelCreate[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };
  
  if (!isNew && isLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <Skeleton width={200} height={32} />
          <Skeleton width="100%" height={400} />
        </div>
      </div>
    );
  }
  
  const isPending = createMutation.isPending || updateMutation.isPending;
  
  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>{isNew ? 'Create Model' : 'Edit Model'}</h1>
        <Button variant="outline" onClick={() => navigate('/admin/models')}>
          Cancel
        </Button>
      </div>
      
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.grid}>
          {/* Left column - Main fields */}
          <div className={styles.card}>
            <h2 className={styles.sectionTitle}>Basic Information</h2>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Alias *</label>
              <Input
                value={formData.alias || ''}
                onChange={(e) => updateField('alias', e.target.value)}
                placeholder="e.g., llm.chat.default"
                disabled={!isNew}
                required
              />
              <span className={styles.hint}>Unique identifier. Cannot be changed after creation.</span>
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Display Name *</label>
              <Input
                value={formData.name || ''}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="e.g., GPT-4 Turbo"
                required
              />
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Type *</label>
              <select
                className={styles.select}
                value={formData.type}
                onChange={(e) => updateField('type', e.target.value as ModelType)}
                disabled={!isNew}
              >
                {MODEL_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Description</label>
              <textarea
                className={styles.textarea}
                value={formData.description || ''}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="Optional description..."
                rows={3}
              />
            </div>
          </div>
          
          {/* Right column - Provider & Config */}
          <div className={styles.card}>
            <h2 className={styles.sectionTitle}>Provider Configuration</h2>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Provider *</label>
              <select
                className={styles.select}
                value={formData.provider}
                onChange={(e) => updateField('provider', e.target.value)}
              >
                {PROVIDERS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Provider Model Name *</label>
              <Input
                value={formData.provider_model_name || ''}
                onChange={(e) => updateField('provider_model_name', e.target.value)}
                placeholder="e.g., gpt-4-turbo-preview"
                required
              />
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Base URL *</label>
              <Input
                value={formData.base_url || ''}
                onChange={(e) => updateField('base_url', e.target.value)}
                placeholder="e.g., https://api.openai.com/v1"
                required
              />
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>API Key Reference</label>
              <Input
                value={formData.api_key_ref || ''}
                onChange={(e) => updateField('api_key_ref', e.target.value)}
                placeholder="e.g., OPENAI_API_KEY"
              />
              <span className={styles.hint}>Environment variable name (not the actual key)</span>
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>Model Version</label>
              <Input
                value={formData.model_version || ''}
                onChange={(e) => updateField('model_version', e.target.value)}
                placeholder="e.g., v1.0"
              />
            </div>
            
            {formData.type === 'embedding' && (
              <div className={styles.formGroup}>
                <label className={styles.label}>Vector Dimensions *</label>
                <Input
                  type="number"
                  value={vectorDim}
                  onChange={(e) => setVectorDim(e.target.value)}
                  placeholder="e.g., 1536"
                  required
                />
              </div>
            )}
          </div>
        </div>
        
        {/* Status section */}
        <div className={styles.card}>
          <h2 className={styles.sectionTitle}>Status & Flags</h2>
          
          <div className={styles.row}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Status</label>
              <select
                className={styles.select}
                value={formData.status}
                onChange={(e) => updateField('status', e.target.value as ModelStatus)}
              >
                {MODEL_STATUSES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            
            <div className={styles.checkboxGroup}>
              <label className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={formData.enabled}
                  onChange={(e) => updateField('enabled', e.target.checked)}
                />
                <span>Enabled</span>
              </label>
              
              <label className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={formData.default_for_type}
                  onChange={(e) => updateField('default_for_type', e.target.checked)}
                />
                <span>Default for type</span>
              </label>
            </div>
          </div>
        </div>
        
        {/* Actions */}
        <div className={styles.actions}>
          <Button variant="outline" type="button" onClick={() => navigate('/admin/models')}>
            Cancel
          </Button>
          <Button type="submit" disabled={isPending}>
            {isPending ? 'Saving...' : isNew ? 'Create Model' : 'Save Changes'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default ModelEditorPage;

/**
 * useRbacRuleEditor — хук для страниц просмотра/редактирования/удаления RBAC правила.
 *
 * Инкапсулирует:
 * - Загрузку правила по id
 * - Мутации update / delete
 * - Управление mode (view / edit)
 * - Состояние confirm-диалога удаления
 */
import { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rbacApi, type RbacEffect, type RbacRule } from '@/shared/api/rbac';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import type { EntityPageMode } from '@/shared/ui';

export function useRbacRuleEditor() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isEditMode ? 'edit' : 'view';

  const [effect, setEffect] = useState<RbacEffect>('deny');
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // ─── Query ───

  const { data: rule, isLoading } = useQuery({
    queryKey: qk.rbac.detail(id!),
    queryFn: () => rbacApi.getRule(id!),
    enabled: !!id,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (rule) setEffect(rule.effect);
  }, [rule]);

  // ─── Mutations ───

  const updateMutation = useMutation({
    mutationFn: () => rbacApi.updateRule(id!, { effect }),
    onSuccess: (updated: RbacRule) => {
      queryClient.setQueryData(qk.rbac.detail(id!), updated);
      queryClient.invalidateQueries({ queryKey: qk.rbac.list({}) });
      queryClient.invalidateQueries({ queryKey: qk.rbac.enrichedRules({}) });
      showSuccess('RBAC правило обновлено');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => rbacApi.deleteRule(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.all() });
      showSuccess('RBAC правило удалено');
      navigate('/admin/rbac');
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ───

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMutation.mutateAsync();
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (rule) setEffect(rule.effect);
    setSearchParams({});
  };

  const handleDelete = () => setShowDeleteConfirm(true);

  const handleDeleteConfirm = () => deleteMutation.mutate();

  return {
    id,
    rule,
    isLoading,
    mode,
    effect,
    setEffect,
    saving,
    showDeleteConfirm,
    setShowDeleteConfirm,
    handleEdit,
    handleSave,
    handleCancel,
    handleDelete,
    handleDeleteConfirm,
    isDeleting: deleteMutation.isPending,
  };
}

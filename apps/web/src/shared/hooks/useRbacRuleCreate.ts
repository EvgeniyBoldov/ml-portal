/**
 * useRbacRuleCreate — хук для страницы создания RBAC правила.
 *
 * Определяет владельца из URL, управляет формой и мутацией создания.
 */
import { useState, useMemo } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { rbacApi, type RbacRuleCreate, type RbacEffect, type ResourceType, type RbacLevel } from '@/shared/api/rbac';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

export interface RbacOwnerInfo {
  level: RbacLevel;
  owner_user_id: string | null;
  owner_tenant_id: string | null;
  owner_platform: boolean;
  title: string;
  backPath: string;
}

export function useRbacRuleCreate() {
  const location = useLocation();
  const { id: ownerId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const [resourceType, setResourceType] = useState<ResourceType>('agent');
  const [resourceId, setResourceId] = useState('');
  const [effect, setEffect] = useState<RbacEffect>('deny');
  const [saving, setSaving] = useState(false);

  // ─── Определяем владельца из URL ───

  const ownerInfo: RbacOwnerInfo = useMemo(() => {
    if (location.pathname.startsWith('/admin/users/') && ownerId) {
      return {
        level: 'user',
        owner_user_id: ownerId,
        owner_tenant_id: null,
        owner_platform: false,
        title: 'Пользователь',
        backPath: `/admin/users/${ownerId}`,
      };
    }
    if (location.pathname.startsWith('/admin/tenants/') && ownerId) {
      return {
        level: 'tenant',
        owner_user_id: null,
        owner_tenant_id: ownerId,
        owner_platform: false,
        title: 'Тенант',
        backPath: `/admin/tenants/${ownerId}`,
      };
    }
    return {
      level: 'platform',
      owner_user_id: null,
      owner_tenant_id: null,
      owner_platform: true,
      title: 'Платформа',
      backPath: '/admin/platform',
    };
  }, [location.pathname, ownerId]);

  // ─── Mutation ───

  const createMutation = useMutation({
    mutationFn: (data: RbacRuleCreate) => rbacApi.createRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.rbac.all() });
      showSuccess('RBAC правило создано');
      navigate(ownerInfo.backPath);
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ───

  const handleResourceTypeChange = (type: ResourceType) => {
    setResourceType(type);
    setResourceId('');
  };

  const handleSave = async () => {
    if (!resourceId) {
      showError('Выберите ресурс');
      return;
    }
    setSaving(true);
    try {
      await createMutation.mutateAsync({
        level: ownerInfo.level,
        resource_type: resourceType,
        resource_id: resourceId,
        effect,
        owner_user_id: ownerInfo.owner_user_id,
        owner_tenant_id: ownerInfo.owner_tenant_id,
        owner_platform: ownerInfo.owner_platform,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => navigate(ownerInfo.backPath);

  return {
    ownerInfo,
    ownerId,
    resourceType,
    resourceId,
    effect,
    saving,
    setResourceId,
    setEffect,
    handleResourceTypeChange,
    handleSave,
    handleCancel,
  };
}

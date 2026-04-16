/**
 * useVersionEditor - Universal hook for versioned entity version pages
 *
 * Encapsulates:
 * - Parent entity query (for breadcrumbs)
 * - Version detail query
 * - Source version query (for duplication)
 * - 5 mutations: create / update / activate / deactivate / delete
 * - Form state sync
 * - Mode detection
 * - Navigation
 */
import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import type { EntityPageMode } from '@/shared/ui';

interface VersionEntity {
  id: string;
  version: number;
}

export interface VersionEditorConfig<TParent, TVersion extends VersionEntity, TForm, TPayload = TForm> {
  slug: string;
  versionParam: string | undefined;
  fromVersionParam?: string | null;

  queryKeys: {
    parentDetail: (slug: string) => readonly unknown[];
    versionsList?: (slug: string) => readonly unknown[];
    versionDetail: (slug: string, version: number) => readonly unknown[];
  };

  api: {
    getParent: (slug: string) => Promise<TParent>;
    getVersion: (slug: string, version: number) => Promise<TVersion>;
    createVersion: (slug: string, data: TPayload) => Promise<TVersion>;
    updateVersion: (slug: string, version: number, data: TPayload) => Promise<TVersion>;
    activateVersion: (slug: string, version: number) => Promise<TVersion>;
    deactivateVersion: (slug: string, version: number) => Promise<TVersion>;
    setRecommendedVersion?: (slug: string, versionId: string) => Promise<void | TParent>;
    deleteVersion?: (slug: string, version: number) => Promise<void>;
  };

  getInitialFormData: (version?: TVersion) => Partial<TForm>;
  buildCreatePayload: (formData: Partial<TForm>, sourceVersion?: TVersion) => TPayload;

  basePath: string;

  messages: {
    created: string;
    updated: string;
    published: string;
    archived: string;
    setRecommended?: string;
    deleted?: string;
  };
}

export function useVersionEditor<
  TParent,
  TVersion extends VersionEntity,
  TForm,
  TPayload = TForm,
>(config: VersionEditorConfig<TParent, TVersion, TForm, TPayload>) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const { slug, versionParam, fromVersionParam } = config;

  const isCreate = !versionParam || versionParam === 'new';
  const versionNumber = isCreate ? 0 : parseInt(versionParam!, 10);
  const fromVersionNumber = fromVersionParam ? parseInt(fromVersionParam, 10) : 0;
  const modeParam = searchParams.get('mode');
  const mode: EntityPageMode = isCreate ? 'create' : (modeParam as EntityPageMode) || 'view';

  const [formData, setFormData] = useState<Partial<TForm>>(config.getInitialFormData());
  const [saving, setSaving] = useState(false);

  // ─── Queries ───

  const { data: parent } = useQuery({
    queryKey: config.queryKeys.parentDetail(slug),
    queryFn: () => config.api.getParent(slug),
    enabled: !!slug,
  });

  const { data: existingVersion, isLoading } = useQuery({
    queryKey: config.queryKeys.versionDetail(slug, versionNumber),
    queryFn: () => config.api.getVersion(slug, versionNumber),
    enabled: !isCreate && !!slug && versionNumber > 0,
  });

  const { data: sourceVersion } = useQuery({
    queryKey: config.queryKeys.versionDetail(slug, fromVersionNumber),
    queryFn: () => config.api.getVersion(slug, fromVersionNumber),
    enabled: isCreate && !!slug && fromVersionNumber > 0,
  });

  // ─── Sync form ───

  useEffect(() => {
    if (isCreate && sourceVersion) {
      setFormData(config.getInitialFormData(sourceVersion));
    } else if (isCreate) {
      setFormData(config.getInitialFormData());
    } else if (existingVersion) {
      setFormData(config.getInitialFormData(existingVersion));
    }
  }, [existingVersion, isCreate, sourceVersion]);

  // ─── Mutations ───

  const invalidateParent = () =>
    queryClient.invalidateQueries({ queryKey: config.queryKeys.parentDetail(slug) as unknown[] });
  const invalidateVersionsList = () => {
    if (config.queryKeys.versionsList) {
      queryClient.invalidateQueries({ queryKey: config.queryKeys.versionsList(slug) as unknown[] });
    }
  };

  const invalidateVersion = () =>
    queryClient.invalidateQueries({
      queryKey: config.queryKeys.versionDetail(slug, versionNumber) as unknown[],
    });

  const createMutation = useMutation({
    mutationFn: (data: TPayload) => config.api.createVersion(slug, data),
    onSuccess: (created) => {
      invalidateParent();
      invalidateVersionsList();
      showSuccess(config.messages.created);
      navigate(`${config.basePath}/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: TPayload) => config.api.updateVersion(slug, versionNumber, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        config.queryKeys.versionDetail(slug, versionNumber),
        updated,
      );
      setFormData(config.getInitialFormData(updated));
      invalidateParent();
      invalidateVersionsList();
      invalidateVersion();
      showSuccess(config.messages.updated);
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => config.api.activateVersion(slug, versionNumber),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        config.queryKeys.versionDetail(slug, versionNumber),
        updated,
      );
      setFormData(config.getInitialFormData(updated));
      invalidateParent();
      invalidateVersionsList();
      invalidateVersion();
      showSuccess(config.messages.published);
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => config.api.deactivateVersion(slug, versionNumber),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        config.queryKeys.versionDetail(slug, versionNumber),
        updated,
      );
      setFormData(config.getInitialFormData(updated));
      invalidateParent();
      invalidateVersionsList();
      invalidateVersion();
      showSuccess(config.messages.archived);
    },
    onError: (err: Error) => showError(err.message),
  });

  const setRecommendedMutation = useMutation({
    mutationFn: () => config.api.setRecommendedVersion?.(slug, existingVersion?.id || '') ?? Promise.resolve(),
    onSuccess: (updatedParent) => {
      if (updatedParent) {
        queryClient.setQueryData(
          config.queryKeys.parentDetail(slug),
          updatedParent,
        );
      }
      invalidateParent();
      invalidateVersionsList();
      showSuccess(config.messages.setRecommended ?? 'Версия сделана основной');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => config.api.deleteVersion?.(slug, versionNumber) ?? Promise.resolve(),
    onSuccess: () => {
      invalidateParent();
      invalidateVersionsList();
      showSuccess(config.messages.deleted ?? 'Версия удалена');
      navigate(`${config.basePath}/${slug}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ───

  const handleFieldChange = (key: string, value: unknown) =>
    setFormData((prev) => ({ ...prev, [key]: value } as Partial<TForm>));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = config.buildCreatePayload(formData, sourceVersion);
      if (isCreate) {
        await createMutation.mutateAsync(payload);
      } else {
        await updateMutation.mutateAsync(payload);
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isCreate) {
      navigate(`${config.basePath}/${slug}`);
    } else {
      if (existingVersion) setFormData(config.getInitialFormData(existingVersion));
      setSearchParams({});
    }
  };

  return {
    // State
    mode,
    isCreate,
    versionNumber,
    formData,
    saving,
    isLoading,

    // Data
    parent,
    existingVersion,
    sourceVersion,

    // Mutations (for loading states in useVersionActions)
    activateMutation,
    deactivateMutation,
    setRecommendedMutation,
    deleteMutation,

    // Handlers
    handleFieldChange,
    handleSave,
    handleEdit,
    handleCancel,

    // Shortcuts
    onActivate: () => activateMutation.mutate(),
    onDeactivate: () => deactivateMutation.mutate(),
    onSetRecommended: () => setRecommendedMutation.mutate(),
    onDelete: () => deleteMutation.mutate(),
    onDuplicate: () => navigate(`${config.basePath}/${slug}/versions/new?from=${versionNumber}`),
  };
}

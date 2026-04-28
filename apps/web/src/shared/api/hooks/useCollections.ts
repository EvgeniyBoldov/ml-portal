import { useSearchParams } from 'react-router-dom';
import type { QueryKey } from '@tanstack/react-query';

import {
  collectionsApi,
  type Collection,
  type CollectionVersion,
  type CollectionVersionCreate,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useVersionEditor } from '@/shared/hooks/useVersionEditor';

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

export function useCollectionVersionEditor(collectionId: string, versionParam: string | undefined) {
  const [searchParams] = useSearchParams();
  const fromVersionParam = searchParams.get('from');

  return useVersionEditor<Collection, CollectionVersion, CollectionVersionCreate>({
    slug: collectionId,
    versionParam,
    fromVersionParam,
    queryKeys: {
      parentDetail: (id) => qk.collections.detail(id) as QueryKey,
      versionsList: (id) => qk.collections.versions(id) as QueryKey,
      versionDetail: (id, v) => qk.collections.version(id, v) as QueryKey,
    },
    api: {
      getParent: collectionsApi.getById,
      getVersion: collectionsApi.getVersion,
      createVersion: collectionsApi.createVersion,
      updateVersion: (id, v, data) => collectionsApi.updateVersion(id, v, data),
      activateVersion: collectionsApi.activateVersion,
      deactivateVersion: collectionsApi.deactivateVersion,
      setRecommendedVersion: collectionsApi.setCurrentVersion,
      deleteVersion: collectionsApi.deleteVersion,
    },
    getInitialFormData: (version) => ({
      data_description: version?.data_description ?? '',
      usage_purpose: version?.usage_purpose ?? '',
      notes: version?.notes ?? '',
    }),
    buildCreatePayload: (formData) => ({
      data_description: toNullableString(formData.data_description),
      usage_purpose: toNullableString(formData.usage_purpose),
      notes: toNullableString(formData.notes),
    }),
    basePath: '/admin/collections',
    messages: {
      created: 'Версия коллекции создана',
      updated: 'Версия коллекции обновлена',
      published: 'Версия коллекции опубликована',
      archived: 'Версия коллекции архивирована',
      deleted: 'Версия коллекции удалена',
    },
  });
}

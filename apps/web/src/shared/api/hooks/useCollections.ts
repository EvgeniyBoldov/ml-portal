import { useSearchParams } from 'react-router-dom';
import type { QueryKey } from '@tanstack/react-query';

import {
  collectionsApi,
  type Collection,
  type CollectionVersion,
  type CollectionVersionCreate,
  type CollectionSemanticProfile,
  type CollectionPolicyHints,
} from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { useVersionEditor } from '@/shared/hooks/useVersionEditor';

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function toString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean);
}

function toMultilineString(value: unknown): string {
  return toStringArray(value).join('\n');
}

function parseMultilineList(value: unknown): string[] {
  if (typeof value !== 'string') return [];
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

function toSemanticProfile(formData: Partial<Record<string, unknown>>): CollectionSemanticProfile {
  return {
    summary: toString(formData.summary).trim(),
    entity_types: toStringArray(formData.entity_types),
    use_cases: toString(formData.use_cases).trim(),
    limitations: toString(formData.limitations).trim(),
    examples: parseMultilineList(formData.examples),
  };
}

function toPolicyHints(formData: Partial<Record<string, unknown>>): CollectionPolicyHints {
  return {
    dos: parseMultilineList(formData.policy_dos),
    donts: parseMultilineList(formData.policy_donts),
    guardrails: parseMultilineList(formData.policy_guardrails),
    citation_rules: parseMultilineList(formData.policy_citation_rules),
    sensitive_fields: parseMultilineList(formData.policy_sensitive_fields),
  };
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
      summary: toString(version?.semantic_profile?.summary),
      entity_types: toStringArray(version?.semantic_profile?.entity_types),
      use_cases: toString(version?.semantic_profile?.use_cases),
      limitations: toString(version?.semantic_profile?.limitations),
      examples: toMultilineString(version?.semantic_profile?.examples),
      policy_dos: toMultilineString(version?.policy_hints?.dos),
      policy_donts: toMultilineString(version?.policy_hints?.donts),
      policy_guardrails: toMultilineString(version?.policy_hints?.guardrails),
      policy_citation_rules: toMultilineString(version?.policy_hints?.citation_rules),
      policy_sensitive_fields: toMultilineString(version?.policy_hints?.sensitive_fields),
      notes: version?.notes ?? '',
    }),
    buildCreatePayload: (formData) => ({
      semantic_profile: toSemanticProfile(formData as Partial<Record<string, unknown>>),
      policy_hints: toPolicyHints(formData as Partial<Record<string, unknown>>),
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

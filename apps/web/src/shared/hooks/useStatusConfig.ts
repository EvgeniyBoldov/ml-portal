import { useMemo } from 'react';

export type EntityType = 'prompt' | 'baseline' | 'policy';

export interface StatusConfig {
  labels: Record<string, string>;
  tones: Record<string, 'warn' | 'success' | 'neutral' | 'info'>;
  options: Array<{
    value: string;
    label: string;
    tone: 'warn' | 'success' | 'neutral' | 'info';
  }>;
}

const STATUS_CONFIGS: Record<EntityType, StatusConfig> = {
  prompt: {
    labels: {
      draft: 'Черновик',
      active: 'Активна',
      archived: 'Архив',
    },
    tones: {
      draft: 'warn',
      active: 'success',
      archived: 'neutral',
    },
    options: [
      { value: 'draft', label: 'Черновик', tone: 'warn' },
      { value: 'active', label: 'Активна', tone: 'success' },
      { value: 'archived', label: 'Архив', tone: 'neutral' },
    ],
  },
  baseline: {
    labels: {
      draft: 'Черновик',
      active: 'Активен',
      archived: 'Архив',
    },
    tones: {
      draft: 'warn',
      active: 'success',
      archived: 'neutral',
    },
    options: [
      { value: 'draft', label: 'Черновик', tone: 'warn' },
      { value: 'active', label: 'Активен', tone: 'success' },
      { value: 'archived', label: 'Архив', tone: 'neutral' },
    ],
  },
  policy: {
    labels: {
      draft: 'Черновик',
      active: 'Активна',
      archived: 'Архив',
    },
    tones: {
      draft: 'warn',
      active: 'success',
      archived: 'neutral',
    },
    options: [
      { value: 'draft', label: 'Черновик', tone: 'warn' },
      { value: 'active', label: 'Активна', tone: 'success' },
      { value: 'archived', label: 'Архив', tone: 'neutral' },
    ],
  },
};

export function useStatusConfig(type: EntityType): StatusConfig {
  return useMemo(() => STATUS_CONFIGS[type], [type]);
}

export default useStatusConfig;

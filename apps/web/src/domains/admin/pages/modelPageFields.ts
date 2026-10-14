import type { FieldConfig } from '@/shared/ui/GridLayout';

export const hasModelCharacteristic = (value: unknown): boolean =>
  typeof value === 'number'
    ? Number.isFinite(value) && value > 0
    : typeof value === 'string' && value.trim().length > 0;

export function modelCharacteristicFields(
  type: string,
  manifest: Record<string, unknown>
): FieldConfig[] {
  const fields: {
    key: string;
    source: string;
    label: string;
    type: 'text' | 'number';
  }[] = [
    {
      key: 'model_version',
      source: 'version',
      label: 'Версия модели',
      type: 'text',
    },
    ...(type === 'llm_chat'
      ? [
          {
            key: 'context_window_tokens',
            source: 'context_window_tokens',
            label: 'Контекстное окно (токены)',
            type: 'number' as const,
          },
        ]
      : []),
    ...(type === 'embedding'
      ? [
          {
            key: 'embedding_dimensions',
            source: 'dimensions',
            label: 'Размерность вектора',
            type: 'number' as const,
          },
        ]
      : []),
    ...(['embedding', 'reranker'].includes(type)
      ? [
          {
            key: 'max_input_tokens',
            source: 'max_tokens',
            label:
              type === 'reranker'
                ? 'Лимит пары запрос/документ (токены)'
                : 'Лимит текста (токены)',
            type: 'number' as const,
          },
        ]
      : []),
  ];
  return fields.map(({ source, ...field }) => {
    const value = manifest[source];
    const reported =
      field.type === 'number'
        ? typeof value === 'number' && Number.isInteger(value) && value > 0
        : hasModelCharacteristic(value);
    return {
      ...field,
      editable: !reported,
      description: reported
        ? 'Получено от сервиса'
        : 'Сервис не сообщил значение — можно заполнить вручную',
    };
  });
}

export const executionFields: FieldConfig[] = [
  {
    key: 'request_timeout_s',
    type: 'number',
    label: 'Таймаут запроса (сек.)',
    placeholder: 'По умолчанию платформы',
  },
  {
    key: 'max_retries',
    type: 'number',
    label: 'Повторы запроса',
    placeholder: 'По умолчанию платформы',
  },
];

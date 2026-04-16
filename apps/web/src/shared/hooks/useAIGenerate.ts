/**
 * useAIGenerate - hook for AI-powered content generation
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { aiGenerateApi, type VersionGenerateRequest } from '@/shared/api/aiGenerate';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';

export interface UseAIGenerateOptions {
  entityType: 'agent' | 'tool';
  entityId: string;
  onSuccess?: (filledFields: Record<string, any>, suggestions: string[]) => void;
}

export function useAIGenerate({ entityType, entityId, onSuccess }: UseAIGenerateOptions) {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const generateMutation = useMutation({
    mutationFn: (data: VersionGenerateRequest) => {
      if (entityType === 'agent') {
        return aiGenerateApi.generateAgentVersion(entityId, data);
      } else {
        return aiGenerateApi.generateToolVersion(entityId, data);
      }
    },
    onSuccess: (response) => {
      showSuccess('Контент сгенерирован успешно');
      onSuccess?.(response.filled_fields, response.suggestions);
    },
    onError: (err: Error) => {
      showError(`Ошибка генерации: ${err.message}`);
    },
  });

  const generate = (data: VersionGenerateRequest) => {
    generateMutation.mutate(data);
  };

  return {
    generate,
    isGenerating: generateMutation.isPending,
    error: generateMutation.error,
  };
}

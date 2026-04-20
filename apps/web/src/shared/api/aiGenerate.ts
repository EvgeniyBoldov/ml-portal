/**
 * AI Generation API - generate content for agent/tool versions
 */
import { apiRequest } from '@/shared/api/http';

export interface VersionGenerateRequest {
  description: string;
  fields: string[];
  context?: Record<string, any>;
}

export interface VersionGenerateResponse {
  filled_fields: Record<string, any>;
  suggestions: string[];
}

export const aiGenerateApi = {
  /**
   * Generate content for agent version
   */
  async generateAgentVersion(
    agentId: string,
    data: VersionGenerateRequest
  ): Promise<VersionGenerateResponse> {
    return apiRequest<VersionGenerateResponse>(
      `/admin/ai-generate/agents/${agentId}/versions/generate`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },
};

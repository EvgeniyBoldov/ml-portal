/**
 * DTO to UI mappers
 * Prepares for OpenAPI schema stabilization
 */

import type {
  RagDocument as ApiRagDocument,
  EmbeddingProgress as ApiEmbeddingProgress,
} from '../api/types/rag';

/**
 * Map API RAG document DTO to UI format
 */
export function mapRagDocDto(dto: any): ApiRagDocument {
  return {
    id: dto.id,
    name: dto.name,
    agg_status: dto.agg_status,
    agg_details_json: dto.agg_details_json,
    scope: dto.scope,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
    tags: dto.tags || [],
    size: dto.size,
    content_type: dto.content_type,
    vectorized_models: dto.vectorized_models || [],
    tenant_name: dto.tenant_name,
    emb_status: dto.emb_status
      ? mapEmbeddingProgressArray(dto.emb_status)
      : undefined,
  };
}

/**
 * Map embedding progress array
 */
export function mapEmbeddingProgressArray(
  dtoArray: any[]
): ApiEmbeddingProgress[] {
  return dtoArray.map(dto => ({
    model: dto.model,
    done: dto.done || 0,
    total: dto.total || 0,
    status: dto.status || 'pending',
    hasError: dto.hasError || false,
    lastError: dto.lastError || dto.last_error,
  }));
}

/**
 * Map API user DTO to UI format
 */
export function mapUserDto(dto: any) {
  return {
    id: dto.id,
    login: dto.login,
    role: dto.role,
    email: dto.email,
    is_active: dto.is_active,
    tenant_id: dto.tenant_id,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
  };
}

/**
 * Map API tenant DTO to UI format
 */
export function mapTenantDto(dto: any) {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    is_active: dto.is_active,
    embed_models: dto.embed_models || [],
    rerank_model: dto.rerank_model,
    ocr: dto.ocr || false,
    layout: dto.layout || false,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
  };
}

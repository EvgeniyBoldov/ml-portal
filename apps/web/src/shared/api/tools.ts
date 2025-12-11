import { apiRequest } from './http';

export interface Tool {
  id: string;
  slug: string;
  name: string;
  description?: string;
  type: 'api' | 'function' | 'database';
  input_schema: Record<string, any>;
  output_schema?: Record<string, any>;
  config?: Record<string, any>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ToolCreate {
  slug: string;
  name: string;
  description?: string;
  type: string;
  input_schema: Record<string, any>;
  output_schema?: Record<string, any>;
  config?: Record<string, any>;
  is_active?: boolean;
}

export interface ToolUpdate {
  name?: string;
  description?: string;
  type?: string;
  input_schema?: Record<string, any>;
  output_schema?: Record<string, any>;
  config?: Record<string, any>;
  is_active?: boolean;
}

export const toolsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    type?: string;
  } = {}): Promise<Tool[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.type) searchParams.set('type', params.type);
    
    return apiRequest(`/admin/tools?${searchParams.toString()}`);
  },

  async get(slug: string): Promise<Tool> {
    return apiRequest(`/admin/tools/${slug}`);
  },

  async create(data: ToolCreate): Promise<Tool> {
    return apiRequest('/admin/tools', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(slug: string, data: ToolUpdate): Promise<Tool> {
    return apiRequest(`/admin/tools/${slug}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(slug: string): Promise<void> {
    return apiRequest(`/admin/tools/${slug}`, {
      method: 'DELETE',
    });
  }
};

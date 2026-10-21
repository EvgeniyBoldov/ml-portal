import { apiRequest } from './http';

export interface MemoryScopeCatalogItem {
  id: string;
  scope_type: string;
  key: string;
  name: string;
  aliases: string[];
  is_all: boolean;
}

export const memoryScopesApi = {
  list: () => apiRequest<MemoryScopeCatalogItem[]>('/memory/scopes'),
};

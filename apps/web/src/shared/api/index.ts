export const API_BASE = (import.meta.env.VITE_API_BASE || '/api') as string;

// Re-export admin API
export * from './admin';

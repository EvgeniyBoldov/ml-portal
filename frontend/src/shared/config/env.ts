export const USE_MOCKS = (import.meta as any).env?.VITE_USE_MOCKS === 'true'
export const API_BASE: string = ((import.meta as any).env?.VITE_API_BASE as string) || 'http://localhost:8000/api'

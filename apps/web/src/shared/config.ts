// apps/web/src/shared/config.ts
// Unified config - single source of truth for all environment variables

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const config = {
  // API endpoints (all under /api/v1)
  apiBaseUrl: API_BASE,
  ragApiUrl: `${API_BASE}/rag`,
  adminApiUrl: `${API_BASE}/admin`,
  authApiUrl: `${API_BASE}/auth`,
  chatsApiUrl: `${API_BASE}/chats`,

  // SSE endpoints
  ragEventsUrl: `${API_BASE}/rag/status/events`,

  // Feature flags
  enableSSELogging:
    import.meta.env.VITE_ENABLE_SSE_LOGGING === 'true' || import.meta.env.DEV,
  enableDevTools: import.meta.env.VITE_ENABLE_DEV_TOOLS === 'true',

  // Cache policies (in ms)
  cacheTimes: {
    list: 60000, // 1 minute for lists
    detail: 30000, // 30 seconds for detail
    sse: 0, // SSE-driven, no cache
  },
  
  // Dev proxy target (for Vite dev server)
  devProxyTarget: import.meta.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
};

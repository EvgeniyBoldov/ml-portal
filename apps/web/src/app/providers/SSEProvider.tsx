import React from 'react';

interface SSEProviderProps {
  children: React.ReactNode;
}

/**
 * SSEProvider — passthrough after legacy RAG global SSE removal.
 * Document-level SSE is now handled locally by StatusModalNew.
 * TODO: remove this wrapper and its usage in AppProviders once confirmed stable.
 */
export function SSEProvider({ children }: SSEProviderProps) {
  return <>{children}</>;
}

export default SSEProvider;

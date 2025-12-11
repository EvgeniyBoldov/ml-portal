import React, { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { SSEClient, SSEMessage } from '@shared/lib/sse';
import { applyRagEvents } from './applyRagEvents';
import { config } from '@shared/config';
import { useAuth } from '@shared/hooks/useAuth';

interface SSEProviderProps {
  children: React.ReactNode;
  url?: string;
}

/**
 * SSEProvider - manages SSE connection for RAG events
 * - Opens connection ONLY when user is authenticated
 * - Batches events every 100ms to avoid UI thrashing
 * - Updates QueryClient cache atomically
 * - Closes connection on unmount or logout
 * - Uses httpOnly cookies for authentication (withCredentials: true)
 */
export function SSEProvider({
  children,
  url = config.ragEventsUrl,
}: SSEProviderProps) {
  const queryClient = useQueryClient();
  const { isAuthenticated, isAuthReady } = useAuth();
  const clientRef = useRef<SSEClient | null>(null);
  const statsRef = useRef({
    totalEvents: 0,
    lastSecond: Date.now(),
    eventsThisSecond: 0,
    droppedEvents: 0,
  });

  useEffect(() => {
    // Don't connect until auth is ready and user is authenticated
    if (!isAuthReady || !isAuthenticated) {
      // Disconnect if was connected
      if (clientRef.current) {
        if (config.enableSSELogging) {
          console.log('[SSE] Disconnecting - user not authenticated');
        }
        clientRef.current.disconnect();
        clientRef.current = null;
      }
      return;
    }

    // Create and connect SSE client
    const client = new SSEClient(
      url,
      (events: SSEMessage[]) => {
        // Logging (dev only)
        if (config.enableSSELogging) {
          const stats = statsRef.current;
          stats.totalEvents += events.length;
          stats.eventsThisSecond += events.length;

          const now = Date.now();
          if (now - stats.lastSecond > 1000) {
            console.log('[SSE]', {
              total: stats.totalEvents,
              lastSecond: stats.eventsThisSecond,
              url,
            });
            stats.eventsThisSecond = 0;
            stats.lastSecond = now;
          }
        }

        // Apply events to cache
        applyRagEvents(events, queryClient);
      }
    );

    clientRef.current = client;

    if (config.enableSSELogging) {
      console.log('[SSE] Connecting to', url);
    }

    client.connect();

    // Cleanup on unmount
    return () => {
      if (config.enableSSELogging) {
        console.log('[SSE] Disconnecting from', url);
      }

      if (clientRef.current) {
        clientRef.current.disconnect();
        clientRef.current = null;
      }
    };
  }, [url, queryClient, isAuthenticated, isAuthReady]);

  return <>{children}</>;
}

export default SSEProvider;

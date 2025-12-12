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

  // Store queryClient in ref to avoid re-creating SSE connection on queryClient changes
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  useEffect(() => {
    // Don't connect until auth is ready and user is authenticated
    if (!isAuthReady || !isAuthenticated) {
      // Disconnect if was connected
      if (clientRef.current) {
        console.log('[SSE] Disconnecting - user not authenticated');
        clientRef.current.disconnect();
        clientRef.current = null;
      }
      return;
    }

    // Already connected - don't reconnect
    if (clientRef.current) {
      console.log('[SSE] Already connected, skipping');
      return;
    }

    // Small delay to ensure cookies are set after auth
    const connectTimeout = setTimeout(() => {
      // Create and connect SSE client
      const client = new SSEClient(
        url,
        (events: SSEMessage[]) => {
          console.log('[SSE] Batch callback received', events.length, 'events');
          
          // Logging (dev only)
          const stats = statsRef.current;
          stats.totalEvents += events.length;
          stats.eventsThisSecond += events.length;

          const now = Date.now();
          if (now - stats.lastSecond > 1000) {
            console.log('[SSE] Stats:', {
              total: stats.totalEvents,
              lastSecond: stats.eventsThisSecond,
              url,
            });
            stats.eventsThisSecond = 0;
            stats.lastSecond = now;
          }

          // Apply events to cache using ref to get latest queryClient
          applyRagEvents(events, queryClientRef.current);
        }
      );

      clientRef.current = client;

      console.log('[SSE] Connecting to', url, { isAuthenticated, isAuthReady });

      client.connect();
    }, 100); // Small delay to ensure cookies are ready

    // Cleanup on unmount
    return () => {
      clearTimeout(connectTimeout);
      console.log('[SSE] Cleanup - disconnecting from', url);

      if (clientRef.current) {
        clientRef.current.disconnect();
        clientRef.current = null;
      }
    };
  }, [url, isAuthenticated, isAuthReady]); // Removed queryClient from deps

  return <>{children}</>;
}

export default SSEProvider;

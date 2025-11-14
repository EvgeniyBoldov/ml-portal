import React, { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { SSEClient, SSEMessage } from '@shared/lib/sse';
import { applyRagEvents } from './applyRagEvents';
import { config } from '@shared/config';

interface SSEProviderProps {
  children: React.ReactNode;
  url?: string;
}

/**
 * SSEProvider - manages SSE connection for RAG events
 * - Opens connection once on mount
 * - Batches events every 100ms to avoid UI thrashing
 * - Updates QueryClient cache atomically
 * - Closes connection on unmount
 * - Uses httpOnly cookies for authentication (withCredentials: true)
 */
export function SSEProvider({
  children,
  url = config.ragEventsUrl,
}: SSEProviderProps) {
  const queryClient = useQueryClient();
  const clientRef = useRef<SSEClient | null>(null);
  const statsRef = useRef({
    totalEvents: 0,
    lastSecond: Date.now(),
    eventsThisSecond: 0,
    droppedEvents: 0,
  });

  useEffect(() => {
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
  }, [url, queryClient]);

  return <>{children}</>;
}

export default SSEProvider;

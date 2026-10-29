import { skipToken, useQuery } from '@tanstack/react-query';
import type { ChatStatusSnapshot } from '@/shared/api/chats';
import { qk } from '@/shared/api/keys';
import { useAuth } from '@/shared/hooks/useAuth';

/** Observe the authenticated global SSE projection without opening another stream. */
export function useChatStatuses() {
  const { user } = useAuth();
  return useQuery<ChatStatusSnapshot[]>({
    queryKey: qk.chats.statuses(user?.id || ''),
    queryFn: skipToken,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

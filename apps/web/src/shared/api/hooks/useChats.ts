import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as chatsApi from '@shared/api/chats';
import { qk } from '@shared/api/keys';
import type { Chat, ChatMessage, ChatMessageCreateRequest } from '@shared/api/types';

/**
 * Hook for fetching chat list
 * Server state managed by TanStack Query
 */
export function useChats(searchQuery?: string) {
  return useQuery({
    queryKey: qk.chats.list(searchQuery),
    queryFn: () => chatsApi.listChats({ q: searchQuery, limit: 100 }),
    staleTime: 30_000, // 30s
  });
}

/**
 * Hook for fetching chat messages
 * TODO: Backend doesn't have GET /chats/{id} for detail, using messages list
 */
export function useChatMessages(chatId: string | undefined, limit = 50) {
  return useQuery({
    queryKey: chatId ? qk.chats.messages(chatId) : ['chats', 'messages', 'undefined'],
    queryFn: () => chatsApi.listMessages(chatId!, limit),
    enabled: !!chatId,
    staleTime: 10_000, // 10s for messages (more dynamic)
  });
}

/**
 * Hook for creating new chat
 */
export function useCreateChat() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ name, tags }: { name?: string; tags?: string[] }) =>
      chatsApi.createChat(name, tags),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
    },
  });
}

/**
 * Hook for deleting chat
 */
export function useDeleteChat() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (chatId: string) => chatsApi.deleteChat(chatId),
    onSuccess: (_result, chatId) => {
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
      queryClient.removeQueries({ queryKey: qk.chats.messages(chatId) });
    },
  });
}

/**
 * Hook for sending message to chat
 */
export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation<
    ChatMessage,
    Error,
    { chatId: string; body: ChatMessageCreateRequest }
  >({
    mutationFn: ({ chatId, body }) => chatsApi.sendMessage(chatId, body),
    onSuccess: (_message, { chatId }) => {
      // Invalidate messages to refetch
      queryClient.invalidateQueries({ queryKey: qk.chats.messages(chatId) });
      // Update last_message_at in list
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
    },
  });
}

/**
 * Hook for renaming chat
 */
export function useRenameChat() {
  const queryClient = useQueryClient();

  return useMutation<Chat, Error, { chatId: string; name: string }>({
    mutationFn: ({ chatId, name }) => chatsApi.renameChat(chatId, name),
    onSuccess: (_chat, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
    },
  });
}

/**
 * Hook for updating chat tags
 */
export function useUpdateChatTags() {
  const queryClient = useQueryClient();

  return useMutation<
    { id: string; tags: string[] },
    Error,
    { chatId: string; tags: string[] }
  >({
    mutationFn: ({ chatId, tags }) => chatsApi.updateChatTags(chatId, tags),
    onSuccess: (_result, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
    },
  });
}

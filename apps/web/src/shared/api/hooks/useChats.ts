import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as chatsApi from '@shared/api/chats';
import { qk } from '@shared/api/keys';
import type { Chat } from '@shared/api/types';

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

/** Bounded, user-safe working context for the selected chat. */
export function useChatContext(chatId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: chatId ? qk.chats.context(chatId) : qk.chats.context('undefined'),
    queryFn: () => chatsApi.getChatContext(chatId!),
    enabled: Boolean(chatId) && enabled,
    staleTime: 30_000,
  });
}

export function useResetChatContext() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (chatId: string) => chatsApi.resetChatContext(chatId),
    onSuccess: (_result, chatId) => {
      queryClient.invalidateQueries({ queryKey: qk.chats.context(chatId) });
    },
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

  return useMutation<{ id: string; deleted: boolean }, Error, string>({
    mutationFn: (chatId: string) => chatsApi.deleteChat(chatId),
    onSuccess: (_result, chatId) => {
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
      queryClient.removeQueries({ queryKey: qk.chats.messages(chatId) });
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
    onSuccess: () => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats', 'list'] });
    },
  });
}

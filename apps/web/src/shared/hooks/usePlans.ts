import { useQuery } from '@tanstack/react-query';
import { plansApi, type PlanStatus } from '@/shared/api';
import { qk } from '@/shared/api/keys';

// Get plans for chat
export const useChatPlans = (chatId: string, status?: PlanStatus) => {
  return useQuery({
    queryKey: qk.plans.chatPlans(chatId, status),
    queryFn: () => plansApi.getChatPlans(chatId, status),
    enabled: !!chatId,
  });
};

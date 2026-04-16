import { apiRequest } from './http';

export type PlanStatus = 'draft' | 'active' | 'completed' | 'failed' | 'paused';

export interface PlannerStep {
  step_id: string;
  kind: 'agent' | 'tool' | 'llm' | 'ask_user';
  title: string;
  description?: string;
  dependencies: string[];
  risk_level: 'low' | 'medium' | 'high' | 'destructive';
  on_fail: 'retry' | 'replan' | 'ask_user' | 'abort';
  requires_confirmation: boolean;
  input: Record<string, any>;
  ref?: string;
  op?: string;
}

export interface PlannerPlan {
  goal: string;
  steps: PlannerStep[];
}

export interface Plan {
  id: string;
  chat_id: string;
  agent_run_id?: string;
  plan_data: PlannerPlan;
  status: PlanStatus;
  current_step: number;
  created_at: string;
  updated_at: string;
}

// API functions
export const plansApi = {
  // Get plans for chat
  getChatPlans: (chatId: string, status?: PlanStatus) =>
    apiRequest<Plan[]>(`/chats/${chatId}/plans`, {
      method: 'GET',
      query: status ? { status } : undefined,
    }),
};

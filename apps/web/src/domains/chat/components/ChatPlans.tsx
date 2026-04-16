import React from 'react';
import { useChatPlans } from '@/shared/hooks/usePlans';
import { PlanVisualization } from '@/shared/ui';
import { Alert } from '@/shared/ui';
import styles from './ChatPlans.module.css';

interface ChatPlansProps {
  chatId: string;
}

export const ChatPlans: React.FC<ChatPlansProps> = ({ chatId }) => {
  const { data: plans, isLoading, error } = useChatPlans(chatId);

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading plans...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <Alert variant="danger">
          Failed to load plans: {error.message}
        </Alert>
      </div>
    );
  }

  if (!plans || plans.length === 0) {
    return null;
  }

  // Show only active and paused plans
  const activePlans = plans.filter(plan => 
    plan.status === 'active' || plan.status === 'paused'
  );

  if (activePlans.length === 0) {
    return null;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h4>Active Plans</h4>
      </div>
      <div className={styles.plansList}>
        {activePlans.map(plan => (
          <PlanVisualization
            key={plan.id}
            plan={plan}
            showActions={true}
          />
        ))}
      </div>
    </div>
  );
};

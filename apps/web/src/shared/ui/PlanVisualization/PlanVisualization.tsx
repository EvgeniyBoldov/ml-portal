import React from 'react';
import { Plan, PlannerStep, PlanStatus } from '@/shared/api';
import Button from '../Button';
import Badge from '../Badge';
import styles from './PlanVisualization.module.css';

interface PlanVisualizationProps {
  plan: Plan;
  onPause?: (planId: string) => void;
  onResume?: (planId: string) => void;
  showActions?: boolean;
}

const statusColors: Record<PlanStatus, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  draft: 'neutral',
  active: 'success',
  completed: 'info',
  failed: 'danger',
  paused: 'warn',
} as const;

const riskLevelColors: Record<string, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  low: 'success',
  medium: 'warn',
  high: 'danger',
  destructive: 'danger',
} as const;

const StepIcon: React.FC<{ step: PlannerStep }> = ({ step }) => {
  const icons = {
    agent: '🤖',
    tool: '🔧',
    llm: '🧠',
    ask_user: '❓',
  };

  return <span className={styles.stepIcon}>{icons[step.kind] || '📋'}</span>;
};

const StepItem: React.FC<{ 
  step: PlannerStep; 
  isActive: boolean; 
  isCompleted: boolean;
  isPaused: boolean;
}> = ({ step, isActive, isCompleted, isPaused }) => {
  return (
    <div 
      className={[
        styles.stepItem,
        isActive && styles.active,
        isCompleted && styles.completed,
        isPaused && styles.paused,
      ].join(' ')}
    >
      <div className={styles.stepHeader}>
        <StepIcon step={step} />
        <div className={styles.stepInfo}>
          <h4 className={styles.stepTitle}>{step.title}</h4>
          <div className={styles.stepMeta}>
            <Badge tone={riskLevelColors[step.risk_level]}>
              {step.risk_level}
            </Badge>
            {step.requires_confirmation && (
              <Badge tone="info">Needs confirmation</Badge>
            )}
          </div>
        </div>
      </div>
      
      {step.description && (
        <p className={styles.stepDescription}>{step.description}</p>
      )}
      
      {step.ref && step.op && (
        <div className={styles.stepDetails}>
          <code>{step.ref}.{step.op}</code>
        </div>
      )}
      
      {step.input && Object.keys(step.input).length > 0 && (
        <div className={styles.stepInput}>
          <strong>Input:</strong>
          <pre>{JSON.stringify(step.input, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export const PlanVisualization: React.FC<PlanVisualizationProps> = ({
  plan,
  onPause,
  onResume,
  showActions = true,
}) => {
  const currentStepIndex = plan.current_step;
  const isPaused = plan.status === 'paused';
  const isActive = plan.status === 'active';
  const isCompleted = plan.status === 'completed';

  const handlePause = () => {
    onPause?.(plan.id);
  };

  const handleResume = () => {
    onResume?.(plan.id);
  };

  return (
    <div className={styles.planVisualization}>
      {/* Header */}
      <div className={styles.planHeader}>
        <div className={styles.planInfo}>
          <h3 className={styles.planGoal}>{plan.plan_data.goal}</h3>
          <div className={styles.planMeta}>
            <Badge tone={statusColors[plan.status]}>
              {plan.status}
            </Badge>
            <span className={styles.stepProgress}>
              Step {currentStepIndex + 1} of {plan.plan_data.steps.length}
            </span>
          </div>
        </div>
        
        {showActions && (
          <div className={styles.planActions}>
            {isActive && (
              <Button variant="outline" size="sm" onClick={handlePause}>
                ⏸️ Pause
              </Button>
            )}
            {isPaused && (
              <Button variant="primary" size="sm" onClick={handleResume}>
                ▶️ Resume
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className={styles.progressBar}>
        <div 
          className={styles.progressFill}
          style={{ 
            width: `${((currentStepIndex + 1) / plan.plan_data.steps.length) * 100}%` 
          }}
        />
      </div>

      {/* Steps */}
      <div className={styles.stepsList}>
        {plan.plan_data.steps.map((step, index) => (
          <StepItem
            key={step.step_id}
            step={step}
            isActive={index === currentStepIndex && isActive}
            isCompleted={index < currentStepIndex || isCompleted}
            isPaused={isPaused && index === currentStepIndex}
          />
        ))}
      </div>

      {/* Footer */}
      <div className={styles.planFooter}>
        <div className={styles.timestamps}>
          <span>Created: {new Date(plan.created_at).toLocaleString()}</span>
          {plan.updated_at !== plan.created_at && (
            <span>Updated: {new Date(plan.updated_at).toLocaleString()}</span>
          )}
        </div>
      </div>
    </div>
  );
};

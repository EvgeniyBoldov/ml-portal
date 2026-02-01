import React from 'react';
import styles from './Stepper.module.css';

export interface Step {
  id: string;
  label: string;
  description?: string;
}

interface StepperProps {
  steps: Step[];
  currentStep: number;
  onStepClick?: (stepIndex: number) => void;
  className?: string;
}

export function Stepper({
  steps,
  currentStep,
  onStepClick,
  className = '',
}: StepperProps) {
  const getStepStatus = (index: number): 'completed' | 'current' | 'upcoming' => {
    if (index < currentStep) return 'completed';
    if (index === currentStep) return 'current';
    return 'upcoming';
  };

  return (
    <div className={[styles.stepper, className].join(' ')}>
      {steps.map((step, index) => {
        const status = getStepStatus(index);
        const isClickable = onStepClick && index < currentStep;

        return (
          <React.Fragment key={step.id}>
            <div
              className={[
                styles.step,
                styles[status],
                isClickable ? styles.clickable : '',
              ].join(' ')}
              onClick={() => isClickable && onStepClick(index)}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onKeyDown={(e) => {
                if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                  onStepClick(index);
                }
              }}
            >
              <div className={styles.indicator}>
                {status === 'completed' ? (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  <span>{index + 1}</span>
                )}
              </div>
              <div className={styles.content}>
                <div className={styles.label}>{step.label}</div>
                {step.description && (
                  <div className={styles.description}>{step.description}</div>
                )}
              </div>
            </div>
            {index < steps.length - 1 && (
              <div
                className={[
                  styles.connector,
                  index < currentStep ? styles.completed : '',
                ].join(' ')}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

export default Stepper;

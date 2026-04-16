import { useEffect, useMemo, useRef, useState } from 'react';
import type { RunStep } from '../hooks/useSandboxRun';
import ChatStepItem from './ChatStepItem';
import styles from './ChatStepsContainer.module.css';

const HIDDEN_STEP_TYPES = new Set(['delta', 'final_content', 'done']);

interface Props {
  steps: RunStep[];
  isStreaming?: boolean;
}

export default function ChatStepsContainer({ steps, isStreaming = false }: Props) {
  const [userToggled, setUserToggled] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const visibleSteps = useMemo(
    () => steps.filter((s) => !HIDDEN_STEP_TYPES.has(s.type)),
    [steps],
  );

  // Auto-expand when streaming starts, collapse when done
  useEffect(() => {
    if (userToggled) return;
    setIsOpen(isStreaming && visibleSteps.length > 0);
  }, [isStreaming, visibleSteps.length, userToggled]);

  // Reset user toggle when a new run starts (steps go to 0→1)
  useEffect(() => {
    if (visibleSteps.length <= 1) {
      setUserToggled(false);
    }
  }, [visibleSteps.length]);

  // Auto-scroll to latest step
  useEffect(() => {
    if (isOpen && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [isOpen, visibleSteps.length]);

  const handleToggle = () => {
    setUserToggled(true);
    setIsOpen((prev) => !prev);
  };

  if (visibleSteps.length === 0) return null;

  return (
    <section className={`${styles.container} ${isStreaming ? styles.streaming : ''}`}>
      <button
        type="button"
        className={styles.header}
        onClick={handleToggle}
        aria-expanded={isOpen}
      >
        <span className={styles.title}>
          Шаги выполнения
          <span className={styles.badge}>{visibleSteps.length}</span>
        </span>
        {isStreaming && <span className={styles.pulse} />}
        <span className={`${styles.chevron} ${isOpen ? styles['chevron-open'] : ''}`}>▾</span>
      </button>
      {isOpen && (
        <div className={styles.content} ref={contentRef}>
          {visibleSteps.map((step, index) => (
            <ChatStepItem key={step.id} step={step} index={index} />
          ))}
        </div>
      )}
    </section>
  );
}

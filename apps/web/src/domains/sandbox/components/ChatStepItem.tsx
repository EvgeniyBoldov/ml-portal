import { useState } from 'react';
import type { RunStep, RunStepType } from '../hooks/useSandboxRun';
import { normalizeTraceEvent } from '@/domains/runtimeTrace/normalize';
import styles from './ChatStepItem.module.css';

interface Props {
  step: RunStep;
  index: number;
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined;
}

const STEP_META: Record<string, { icon: string; tone: string }> = {
  input: { icon: '○', tone: 'neutral' },
  decision: { icon: '⇢', tone: 'info' },
  planner: { icon: '▸', tone: 'info' },
  retry: { icon: '↺', tone: 'warn' },
  llm: { icon: '◈', tone: 'info' },
  operation: { icon: '⚙', tone: 'info' },
  policy: { icon: '⛨', tone: 'warn' },
  budget: { icon: '◷', tone: 'warn' },
  final: { icon: '✓', tone: 'success' },
  error: { icon: '✕', tone: 'error' },
  system: { icon: '·', tone: 'neutral' },
  intent: { icon: '✨', tone: 'info' }, // High-level intent descriptions
};

function StepBody({ step }: { step: RunStep }) {
  const d = step.data;
  const inputData = d.input ?? d.arguments ?? d.parameters ?? d.payload ?? d.arguments_preview;
  const outputData = d.output ?? d.result ?? d.data ?? d.response ?? d.result_preview;

  switch (step.type as RunStepType) {
    case 'routing':
      return (
        <div className={styles.body}>
          <div className={styles.row}>
            <span className={styles.label}>Агент</span>
            <span className={styles.value}>{stringifyValue(d.agent_slug)}</span>
          </div>
          {hasValue(d.execution_path) && (
            <div className={styles.row}>
              <span className={styles.label}>Путь</span>
              <span className={styles.badge}>{stringifyValue(d.execution_path)}</span>
            </div>
          )}
          {hasValue(d.mode) && (
            <div className={styles.row}>
              <span className={styles.label}>Режим</span>
              <span className={styles.badge}>{stringifyValue(d.mode)}</span>
            </div>
          )}
          {Array.isArray(d.available_tools) && d.available_tools.length > 0 && (
            <div className={styles.row}>
              <span className={styles.label}>Инструменты</span>
              <span className={styles.tags}>
                {(d.available_tools as string[]).map((t) => (
                  <span key={t} className={styles.tag}>{t}</span>
                ))}
              </span>
            </div>
          )}
        </div>
      );

    case 'intent':
      return (
        <div className={styles.body}>
          <div className={styles.row}>
            <span className={styles.label}>Действие</span>
            <span className={styles.value}>{stringifyValue(d.description)}</span>
          </div>
          {hasValue(d.details) && typeof d.details === 'object' && d.details !== null && Object.keys(d.details).length > 0 && (
            <div className={styles.row}>
              <span className={styles.label}>Детали</span>
              <pre className={styles.code}>{stringifyValue(d.details)}</pre>
            </div>
          )}
        </div>
      );

    case 'tool_call':
      return (
        <div className={styles.body}>
          <div className={styles.row}>
            <span className={styles.label}>Инструмент</span>
            <span className={styles.mono}>{stringifyValue(d.tool)}</span>
          </div>
          {inputData !== undefined && (
            <>
              <div className={styles.row}>
                <span className={styles.label}>Вход</span>
              </div>
              <pre className={styles.code}>{stringifyValue(inputData)}</pre>
            </>
          )}
        </div>
      );

    case 'tool_result': {
      const success = Boolean(d.success);
      return (
        <div className={styles.body}>
          <div className={styles.row}>
            <span className={styles.label}>Инструмент</span>
            <span className={styles.mono}>{stringifyValue(d.tool)}</span>
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Статус</span>
            <span className={success ? styles['badge-success'] : styles['badge-error']}>
              {success ? 'Успех' : 'Ошибка'}
            </span>
          </div>
          {outputData !== undefined && (
            <>
              <div className={styles.row}>
                <span className={styles.label}>Выход</span>
              </div>
              <pre className={styles.code}>{stringifyValue(outputData)}</pre>
            </>
          )}
        </div>
      );
    }

    case 'planner_action':
      return (
        <div className={styles.body}>
          {hasValue(d.iteration) && (
            <div className={styles.row}>
              <span className={styles.label}>Итерация</span>
              <span className={styles.value}>{stringifyValue(d.iteration)}</span>
            </div>
          )}
          <div className={styles.row}>
            <span className={styles.label}>Действие</span>
            <span className={styles.badge}>{stringifyValue(d.action_type)}</span>
          </div>
          {hasValue(d.tool_slug) && (
            <div className={styles.row}>
              <span className={styles.label}>Инструмент</span>
              <span className={styles.mono}>{stringifyValue(d.tool_slug)}</span>
            </div>
          )}
          {hasValue(d.op) && (
            <div className={styles.row}>
              <span className={styles.label}>Операция</span>
              <span className={styles.value}>{stringifyValue(d.op)}</span>
            </div>
          )}
        </div>
      );

    case 'policy_decision':
      return (
        <div className={styles.body}>
          <div className={styles.row}>
            <span className={styles.label}>Решение</span>
            <span className={styles.badge}>{stringifyValue(d.decision ?? d)}</span>
          </div>
          {hasValue(d.reason) && (
            <div className={styles.row}>
              <span className={styles.label}>Причина</span>
              <span className={styles.value}>{stringifyValue(d.reason)}</span>
            </div>
          )}
        </div>
      );

    case 'confirmation_required':
      return (
        <div className={styles.body}>
          {hasValue(d.reason) && (
            <div className={styles.row}>
              <span className={styles.label}>Причина</span>
              <span className={styles.value}>{stringifyValue(d.reason)}</span>
            </div>
          )}
          {hasValue(d.action) && (
            <pre className={styles.code}>{stringifyValue(d.action)}</pre>
          )}
        </div>
      );

    case 'waiting_input':
      return (
        <div className={styles.body}>
          {hasValue(d.question) && (
            <div className={styles.text}>{stringifyValue(d.question)}</div>
          )}
          {hasValue(d.reason) && (
            <div className={styles.row}>
              <span className={styles.label}>Причина</span>
              <span className={styles.value}>{stringifyValue(d.reason)}</span>
            </div>
          )}
        </div>
      );

    case 'stop':
      return (
        <div className={styles.body}>
          {hasValue(d.reason) && (
            <div className={styles.row}>
              <span className={styles.label}>Причина</span>
              <span className={styles.value}>{stringifyValue(d.reason)}</span>
            </div>
          )}
          {hasValue(d.message) && (
            <div className={styles.text}>{stringifyValue(d.message)}</div>
          )}
        </div>
      );

    case 'error':
      return (
        <div className={styles.body}>
          <div className={styles['error-text']}>{stringifyValue(d.error ?? d)}</div>
        </div>
      );

    case 'status':
      return (
        <div className={styles.body}>
          <span className={styles.value}>{stringifyValue(d.stage ?? d)}</span>
        </div>
      );

    default:
      return (
        <div className={styles.body}>
          <pre className={styles.code}>{stringifyValue(d)}</pre>
        </div>
      );
  }
}

export default function ChatStepItem({ step, index }: Props) {
  const semantic = normalizeTraceEvent({
    id: step.id,
    raw_type: step.type,
    data: step.data,
    step_number: index,
    duration_ms: typeof step.data.duration_ms === 'number' ? step.data.duration_ms : undefined,
  });
  const meta = STEP_META[semantic.category] ?? STEP_META.system;
  const isMinor = step.type === 'status' || step.type === 'delta';
  const [isOpen, setIsOpen] = useState(!isMinor);

  return (
    <div className={`${styles.step} ${styles[`tone-${meta.tone}`] ?? ''}`}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
      >
        <span className={styles.icon}>{meta.icon}</span>
        <span className={styles.title}>{semantic.title}</span>
        <span className={`${styles.chevron} ${isOpen ? styles['chevron-open'] : ''}`}>▾</span>
      </button>
      {isOpen && <StepBody step={step} />}
    </div>
  );
}

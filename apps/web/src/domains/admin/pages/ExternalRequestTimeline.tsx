import type {
  ExternalRequestDetail,
  ExternalRequestTimelineItem,
} from '@/shared/api/externalRequests';
import { Badge, Icon } from '@/shared/ui';
import MarkdownRenderer from '@/shared/ui/MarkdownRenderer';

import { runStatusLabel, runStatusTone } from './agentRunStatus';
import styles from './ExternalRequestPage.module.css';

const dateTime = new Intl.DateTimeFormat('ru-RU', {
  dateStyle: 'short',
  timeStyle: 'medium',
});

export function duration(start: string, end: string | number): string {
  const milliseconds = Math.max(
    0,
    (typeof end === 'number' ? end : Date.parse(end)) - Date.parse(start)
  );
  const seconds = Math.floor(milliseconds / 1000);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days} д ${hours} ч`;
  if (hours) return `${hours} ч ${minutes} мин`;
  if (minutes) return `${minutes} мин ${seconds % 60} с`;
  return seconds ? `${seconds} с` : '< 1 с';
}

export function Timestamp({ value }: { value: string }) {
  return <time dateTime={value}>{dateTime.format(new Date(value))}</time>;
}

const stepLabels: Record<string, string> = {
  accepted: 'Поручение принято',
  waiting_input: 'Уточняющий вопрос',
  waiting_confirmation: 'Запрос подтверждения',
  waiting_timer: 'Пауза по таймеру',
  timer_elapsed: 'Таймер сработал',
  answer: 'Ответ пользователя',
  completed: 'Итоговый ответ',
  failed: 'Ошибка выполнения',
  cancelled: 'Поручение отменено',
};

const deliveryLabels: Record<string, string> = {
  pending: 'Ожидает доставки',
  sending: 'Доставляется',
  delivered: 'Доставлено',
  failed: 'Ошибка доставки',
};

function TimelineStep({
  step,
  acceptedAt,
}: {
  step: ExternalRequestTimelineItem;
  acceptedAt: string;
}) {
  const isReply = step.kind === 'answer';
  const hasMessage =
    Boolean(step.text?.trim()) ||
    (step.answer !== null && step.answer !== undefined);
  const tone = isReply ? 'info' : runStatusTone(step.kind);
  const title =
    step.kind === 'waiting_timer' && hasMessage
      ? 'Промежуточный ответ'
      : step.kind === 'completed' && !hasMessage
        ? 'Поручение завершено'
        : (stepLabels[step.kind] ?? runStatusLabel[step.kind] ?? step.kind);
  const deliveryStatus = step.delivery_status;
  const answer =
    typeof step.answer === 'boolean'
      ? step.answer
        ? 'Да'
        : 'Нет'
      : step.answer;

  return (
    <li
      className={styles.step}
      data-tone={tone}
      data-direction={
        isReply ? 'incoming' : hasMessage ? 'outgoing' : undefined
      }
    >
      <span className={styles.marker} aria-hidden="true">
        <Icon
          name={isReply ? 'user' : hasMessage ? 'bot' : 'activity'}
          size={14}
        />
      </span>
      <div className={styles['step-header']}>
        <h3>{title}</h3>
        <div className={styles['step-time']}>
          <Timestamp value={step.occurred_at} />
          {step.kind !== 'accepted' && (
            <span title="Время с момента принятия">
              +{duration(acceptedAt, step.occurred_at)}
            </span>
          )}
        </div>
      </div>
      {step.text?.trim() && (
        <div className={styles.message}>
          <MarkdownRenderer
            content={step.text}
            allowImages={false}
            enableSyntaxHighlighting={false}
          />
        </div>
      )}
      {isReply && (
        <div className={styles.message}>
          <p className={styles['plain-text']}>
            {answer?.trim() ? answer : 'Текст ответа отсутствует.'}
          </p>
        </div>
      )}
      {(deliveryStatus || step.wake_at || step.resolved_at) && (
        <div className={styles['step-details']}>
          {deliveryStatus && (
            <Badge
              size="sm"
              tone={
                deliveryStatus === 'delivered'
                  ? 'success'
                  : deliveryStatus === 'failed'
                    ? 'danger'
                    : 'neutral'
              }
            >
              {deliveryLabels[deliveryStatus] ?? deliveryStatus}
            </Badge>
          )}
          {step.delivered_at && (
            <span title="Время и задержка доставки">
              <Timestamp value={step.delivered_at} /> · задержка{' '}
              {duration(step.occurred_at, step.delivered_at)}
            </span>
          )}
          {step.delivery_attempts > 1 && (
            <span>Попыток доставки: {step.delivery_attempts}</span>
          )}
          {step.wake_at && (
            <span>
              Таймер на <Timestamp value={step.wake_at} />
            </span>
          )}
          {step.resolved_at && (
            <span>Ожидание {duration(step.occurred_at, step.resolved_at)}</span>
          )}
        </div>
      )}
    </li>
  );
}

export function ExternalRequestTimeline({
  request,
}: {
  request: ExternalRequestDetail;
}) {
  return (
    <ol
      className={styles.timeline}
      aria-label="Сообщения и события поручения"
      role="list"
    >
      <li className={styles.step} data-tone="info" data-direction="incoming">
        <span className={styles.marker} aria-hidden="true">
          <Icon name="user" size={14} />
        </span>
        <div className={styles['step-header']}>
          <div>
            <h3>Входящее сообщение</h3>
            <p className={styles.sender}>{request.user_name}</p>
          </div>
          <div className={styles['step-time']}>
            <Timestamp value={request.created_at} />
          </div>
        </div>
        <div className={styles.message}>
          <p className={styles['plain-text']}>
            {request.text.trim() ? request.text : 'Текст запроса отсутствует.'}
          </p>
        </div>
      </li>
      {request.timeline.map(step => (
        <TimelineStep
          key={step.id}
          step={step}
          acceptedAt={request.created_at}
        />
      ))}
    </ol>
  );
}

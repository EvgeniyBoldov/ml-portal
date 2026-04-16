import MarkdownRenderer from '@/shared/ui/MarkdownRenderer';
import styles from './ChatAnswerCard.module.css';

interface Props {
  text: string;
  isRunning: boolean;
}

export default function ChatAnswerCard({ text, isRunning }: Props) {
  const hasContent = text.length > 0;
  if (!hasContent && !isRunning) return null;

  return (
    <article className={`${styles.card} ${isRunning ? styles.streaming : ''}`}>
      <div className={styles.header}>
        <span className={styles.label}>Ответ</span>
        {isRunning && (
          <span className={styles.indicator}>
            <span className={styles.dot} />
            <span className={styles.dot} />
            <span className={styles.dot} />
          </span>
        )}
      </div>
      <div className={styles.content}>
        {hasContent ? (
          <MarkdownRenderer content={text} enableSyntaxHighlighting={!isRunning} />
        ) : (
          <span className={styles.placeholder}>Формируем ответ...</span>
        )}
        {isRunning && hasContent && <span className={styles.cursor}>▊</span>}
      </div>
    </article>
  );
}

import styles from './ChatQuestionCard.module.css';

interface Props {
  text: string;
}

export default function ChatQuestionCard({ text }: Props) {
  return (
    <article className={styles.card}>
      <div className={styles.label}>Вопрос</div>
      <div className={styles.content}>{text}</div>
    </article>
  );
}

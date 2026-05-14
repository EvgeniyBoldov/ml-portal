import styles from './Inspector.module.css';

interface InspectorEmptyProps {
  message: string;
}

export function InspectorEmpty({ message }: InspectorEmptyProps) {
  return (
    <div className={styles.empty}>
      <p>{message}</p>
    </div>
  );
}

import React from 'react';
import styles from './ChatProgressBlock.module.css';

interface ChatProgressBlockProps {
  lines: Array<{ id: string; text: string }>;
}

export function ChatProgressBlock({ lines }: ChatProgressBlockProps) {
  if (!lines.length) return null;
  return (
    <div className={styles.block} aria-live="polite">
      {lines.map((line) => (
        <div className={styles.line} key={line.id}>
          {line.text}
        </div>
      ))}
    </div>
  );
}

export default ChatProgressBlock;

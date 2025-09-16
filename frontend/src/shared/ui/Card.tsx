import React from 'react';
import styles from './Card.module.css';

export default function Card({
  className = '',
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={[styles.card, className].join(' ')} />;
}

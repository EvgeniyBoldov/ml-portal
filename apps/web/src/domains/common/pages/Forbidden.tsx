import React from 'react';
import { Link } from 'react-router-dom';
import styles from './Forbidden.module.css';

export default function Forbidden() {
  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <h1 className={styles.code}>403</h1>
        <h2 className={styles.title}>Доступ запрещён</h2>
        <p className={styles.message}>
          У вас нет прав для доступа к этой странице.
        </p>
        <Link to="/gpt/chat" className={styles.link}>
          Вернуться к чатам
        </Link>
      </div>
    </div>
  );
}

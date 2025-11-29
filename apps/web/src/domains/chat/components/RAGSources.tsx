import React from 'react';
import styles from './RAGSources.module.css';

interface Source {
  source_id: string;
  chunk_id: string;
  text: string;
  page?: number;
  score?: number;
  meta?: any;
}

interface RAGSourcesProps {
  sources: Source[];
}

export default function RAGSources({ sources }: RAGSourcesProps) {
  if (!sources || !Array.isArray(sources) || sources.length === 0) return null;

  return (
    <details className={styles.container}>
      <summary className={styles.summary}>
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          width="16" 
          height="16" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round"
        >
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
        <span>Использовано {sources.length} источников</span>
      </summary>
      <div className={styles.list}>
        {sources.map((source, idx) => (
          <div key={`${source.source_id}-${idx}`} className={styles.item}>
            <div className={styles.itemHeader}>
              <span>Документ {idx + 1} {source.page ? `(стр. ${source.page})` : ''}</span>
              {typeof source.score === 'number' && (
                <span className={styles.score}>{(source.score * 100).toFixed(0)}%</span>
              )}
            </div>
            <div className={styles.snippet}>
              {source.text}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

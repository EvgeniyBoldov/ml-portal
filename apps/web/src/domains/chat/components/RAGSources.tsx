import React, { useCallback } from 'react';
import { apiRequest } from '@shared/api/http';
import styles from './RAGSources.module.css';

interface Source {
  source_id: string;
  source_name?: string;
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
  const handleDownload = useCallback(async (sourceId: string, kind: 'original' | 'canonical') => {
    try {
      const response = await apiRequest<{ url: string }>(
        `/rag/${sourceId}/download?kind=${kind}`
      );
      if (response.url) {
        window.open(response.url, '_blank');
      }
    } catch (error) {
      console.error('Failed to get download URL:', error);
    }
  }, []);

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
              <span className={styles.sourceName}>
                {source.source_name || `Документ ${idx + 1}`}
                {source.page !== undefined && source.page !== null && ` (стр. ${source.page})`}
              </span>
              {typeof source.score === 'number' && (
                <span className={styles.score}>{(source.score * 100).toFixed(0)}%</span>
              )}
            </div>
            <div className={styles.snippet}>
              {source.text}
            </div>
            <div className={styles.actions}>
              <button 
                className={styles.downloadBtn}
                onClick={() => handleDownload(source.source_id, 'original')}
                title="Скачать оригинал"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Оригинал
              </button>
              <button 
                className={styles.downloadBtn}
                onClick={() => handleDownload(source.source_id, 'canonical')}
                title="Скачать обработанный"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
                Текст
              </button>
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

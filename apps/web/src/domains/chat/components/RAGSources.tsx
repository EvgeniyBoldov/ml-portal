import React, { useCallback, useState } from 'react';
import { Icon } from '@/shared/ui/Icon';
import { buildFileDownloadUrl, buildRagDocFileId } from '@shared/api/files';
import styles from './RAGSources.module.css';

export interface RAGSource {
  source_id?: string;
  source_name?: string;
  chunk_id?: string;
  text?: string;
  page?: number;
  score?: number;
  meta?: any;
}

interface RAGSourcesProps {
  sources: RAGSource[];
}

export default function RAGSources({ sources }: RAGSourcesProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const handleDownload = useCallback(async (sourceId: string, kind: 'original' | 'canonical') => {
    try {
      const fileId = buildRagDocFileId(sourceId, kind);
      window.open(buildFileDownloadUrl(fileId), '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.error('Failed to get download URL:', error);
    }
  }, []);

  if (!sources || !Array.isArray(sources) || sources.length === 0) return null;

  return (
    <details className={styles.container}>
      <summary className={styles.summary}>
        <Icon name="book-open" size={14} />
        <span>{sources.length} источник{sources.length === 1 ? '' : sources.length < 5 ? 'а' : 'ов'}</span>
      </summary>
      <div className={styles.list}>
        {sources.map((source, idx) => {
          const isExpanded = expandedIdx === idx;
          const name = source.source_name || `Документ ${idx + 1}`;
          const hasDownload = !!source.source_id;

          return (
            <div
              key={`${source.source_id || idx}-${idx}`}
              className={`${styles.item} ${isExpanded ? styles.itemExpanded : ''}`}
            >
              <button
                className={styles.itemHeader}
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              >
                <Icon name="file-text" size={14} className={styles.fileIcon} />
                <span className={styles.sourceName}>
                  {name}
                  {source.page != null && source.page > 0 && (
                    <span className={styles.pageNum}> стр. {source.page}</span>
                  )}
                </span>
                {typeof source.score === 'number' && (
                  <span className={styles.score}>{(source.score * 100).toFixed(0)}%</span>
                )}
                <Icon
                  name={isExpanded ? 'chevron-up' : 'chevron-down'}
                  size={12}
                  className={styles.chevron}
                />
              </button>

              {isExpanded && (
                <div className={styles.itemBody}>
                  {source.text && (
                    <div className={styles.snippet}>{source.text}</div>
                  )}
                  {hasDownload && (
                    <div className={styles.actions}>
                      <button
                        className={styles.downloadBtn}
                        onClick={() => handleDownload(source.source_id!, 'original')}
                        title="Скачать оригинал"
                      >
                        <Icon name="download" size={12} />
                        Оригинал
                      </button>
                      <button
                        className={styles.downloadBtn}
                        onClick={() => handleDownload(source.source_id!, 'canonical')}
                        title="Скачать обработанный текст"
                      >
                        <Icon name="file" size={12} />
                        Текст
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}

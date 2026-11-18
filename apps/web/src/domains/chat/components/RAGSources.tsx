import React, { useCallback, useState } from 'react';
import { Icon } from '@/shared/ui/Icon';
import { buildArtifactDownloadUrl, buildFileDownloadUrl, buildRagDocFileId } from '@shared/api/files';
import type { ChatRagSource } from '../types';
import styles from './RAGSources.module.css';

export type RAGSource = ChatRagSource;

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
          const explicitKind = source.kind || source.source_type;
          const artifactId = source.artifact_id ||
            (source.artifact && typeof source.artifact === 'object' &&
            'artifact_id' in source.artifact && typeof source.artifact.artifact_id === 'string'
              ? source.artifact.artifact_id : undefined);
          const documentId = !artifactId && !source.url
            ? source.document_id ||
              (explicitKind === 'rag_document' || explicitKind === 'rag'
                ? source.source_id
                : !explicitKind && (source.chunk_id || source.page != null)
                  ? source.source_id
                  : undefined)
            : undefined;

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
                  {(source.excerpt || source.text) && (
                    <div className={styles.snippet}>
                      {source.excerpt || source.text}{source.excerpt_truncated ? '…' : ''}
                    </div>
                  )}
                  {source.url && !artifactId && (
                    <div className={styles.actions}>
                      <a className={styles.downloadBtn} href={source.url} target="_blank" rel="noreferrer">
                        Открыть источник
                      </a>
                    </div>
                  )}
                  {artifactId && (
                    <div className={styles.actions}>
                      <a className={styles.downloadBtn} href={buildArtifactDownloadUrl(artifactId)} target="_blank" rel="noreferrer">
                        <Icon name="download" size={12} /> Скачать файл
                      </a>
                    </div>
                  )}
                  {documentId && (
                    <div className={styles.actions}>
                      <button
                        className={styles.downloadBtn}
                        onClick={() => handleDownload(documentId, 'original')}
                        title="Скачать оригинал"
                      >
                        <Icon name="download" size={12} />
                        Оригинал
                      </button>
                      <button
                        className={styles.downloadBtn}
                        onClick={() => handleDownload(documentId, 'canonical')}
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

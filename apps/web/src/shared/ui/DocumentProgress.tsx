// apps/web/src/shared/ui/DocumentProgress.tsx
import React from 'react';
import { getStatusGraph } from '@shared/api/rag';
import { StatusGraph } from '@shared/api/types/rag';
import { useToast } from '@shared/ui/Toast';
import { useQuery } from '@tanstack/react-query';
import { statusToClass, statusToLabel } from '@shared/lib/ragStatus';
import { qk } from '@shared/api/keys';
import styles from './DocumentProgress.module.css';

interface DocumentProgressProps {
  sourceId: string;
  className?: string;
  onClick?: () => void;
}

const getStatusColor = (status: string) => {
  return statusToClass(status as any).dotClass;
};

const getStatusText = (status: string) => statusToLabel(status as any);

export function DocumentProgressComponent({
  sourceId,
  className,
  onClick,
}: DocumentProgressProps) {
  const { showToast } = useToast();

  const {
    data: statusGraph,
    isLoading,
    error,
  } = useQuery<StatusGraph, Error>({
    queryKey: qk.rag.statusGraph(sourceId),
    queryFn: () => getStatusGraph(sourceId),
    enabled: !!sourceId,
    // No polling - updates come from SSE
    onError: err => {
      showToast(`Ошибка загрузки статуса: ${err.message}`, 'error');
    },
  });

  if (isLoading) {
    return (
      <div className={`${styles.container} ${className || ''}`}>
        <div className={`${styles.dot} ${styles.loading}`}></div>
      </div>
    );
  }

  if (error || !statusGraph) {
    return (
      <div className={`${styles.container} ${className || ''}`}>
        <div className={`${styles.dot} ${styles.error}`}></div>
      </div>
    );
  }

  const aggStatus = statusGraph.agg_status;

  const containerClasses = [
    styles.container,
    onClick ? styles.clickable : '',
    className || '',
  ].filter(Boolean).join(' ');

  return (
    <div
      className={containerClasses}
      onClick={onClick}
      title={`Статус: ${getStatusText(aggStatus)}`}
    >
      <div className={`${styles.dot} ${getStatusColor(aggStatus)}`}></div>
    </div>
  );
}

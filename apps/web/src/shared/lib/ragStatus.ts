/**
 * RAG Status utilities
 * Centralized status mapping, colors, and derived flags
 */

export type RAGStatus =
  | 'uploaded'
  | 'processing'
  | 'normalized'
  | 'chunked'
  | 'embedding'
  | 'ready'
  | 'failed'
  | 'archived';

// Derived states - not backend statuses, computed from embedding progress
export interface EmbeddingProgress {
  model: string;
  done: number;
  total: number;
  status: string;
  hasError?: boolean;
}

/**
 * Checks if document is partially ready (some embeddings done, some not)
 * This is a DERIVED state, not a backend status
 */
export const isPartial = (embeddings: EmbeddingProgress[]): boolean => {
  if (!embeddings || embeddings.length === 0) return false;

  const hasInProgress = embeddings.some(
    e => e.status === 'processing' || e.status === 'running'
  );
  const hasCompleted = embeddings.some(
    e => e.status === 'ok' || e.status === 'completed'
  );

  // Partial if we have both completed and in-progress embeddings
  return hasCompleted && hasInProgress;
};

export const isTerminal = (status: RAGStatus): boolean => {
  return status === 'ready' || status === 'failed' || status === 'archived';
};

export interface ModelProgress {
  model: string;
  done: number;
  total: number;
  hasError: boolean;
}

export const hasProgressWarning = (
  modelsProgress: ModelProgress[]
): boolean => {
  return modelsProgress.some(m => m.done < m.total || m.hasError);
};

export const statusToBadgeColor = (
  status: RAGStatus,
  warning: boolean = false
): 'green' | 'blue' | 'gray' | 'red' | 'yellow' => {
  if (warning) {
    return 'yellow';
  }

  switch (status) {
    case 'uploaded':
      return 'blue';
    case 'processing':
      return 'blue';
    case 'normalized':
      return 'blue';
    case 'chunked':
      return 'blue';
    case 'embedding':
      return 'blue';
    case 'ready':
      return 'green';
    case 'failed':
      return 'red';
    case 'archived':
      return 'gray';
    default:
      return 'gray';
  }
};

export const statusToLabel = (status: RAGStatus): string => {
  const labels: Record<RAGStatus, string> = {
    uploaded: 'Загружено',
    processing: 'В обработке',
    normalized: 'Нормализовано',
    chunked: 'Разбито на фрагменты',
    embedding: 'Создание векторов',
    ready: 'Готово',
    failed: 'Ошибка',
    archived: 'Архивировано',
  };

  return labels[status] || status;
};

export const statusToIcon = (status: RAGStatus): string => {
  switch (status) {
    case 'ready':
    case 'normalized':
    case 'chunked':
      return '✓';
    case 'uploaded':
    case 'processing':
    case 'embedding':
      return '●';
    case 'failed':
      return '!';
    case 'archived':
      return '−';
    default:
      return '−';
  }
};

export const canRetry = (status: RAGStatus): boolean => {
  return status === 'failed';
};

export const canCancel = (status: RAGStatus): boolean => {
  return (
    status === 'uploaded' ||
    status === 'processing' ||
    status === 'normalized' ||
    status === 'chunked' ||
    status === 'embedding'
  );
};

export interface StatusClasses {
  badgeClass: string;
  dotClass: string;
}

export function statusToClass(
  status: RAGStatus,
  options?: { partial?: boolean; variant?: 'badge' | 'dot' }
): StatusClasses {
  const { partial = false } = options || {};
  const color = statusToBadgeColor(status, partial);

  const colorMap = {
    green: {
      badge: 'bg-green-500',
      dot: 'bg-green-500',
    },
    blue: {
      badge: 'bg-blue-500',
      dot: 'bg-blue-500',
    },
    gray: {
      badge: 'bg-gray-400',
      dot: 'bg-gray-400',
    },
    red: {
      badge: 'bg-red-500',
      dot: 'bg-red-500',
    },
    yellow: {
      badge: 'bg-yellow-500',
      dot: 'bg-yellow-500',
    },
  };

  const classes = colorMap[color] || colorMap.gray;

  return {
    badgeClass: classes.badge,
    dotClass: classes.dot,
  };
}

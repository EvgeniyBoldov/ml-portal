// apps/web/src/components/common/StatusBadge.tsx
import React from 'react';
import { RAGStatus, statusToBadgeColor, statusToLabel } from '@shared/lib/ragStatus';

interface StatusBadgeProps {
  status: RAGStatus;
  className?: string;
}

const getStatusConfig = (status: RAGStatus) => {
  const color = statusToBadgeColor(status, false);
  const isWarning = color === 'yellow';
  const variant = isWarning ? 'outline' : 'solid';
  const mappedColor = color === 'gray' ? 'gray' : color;

  return {
    text: statusToLabel(status),
    variant,
    color: mappedColor,
  };
};

const getVariantStyles = (variant: 'solid' | 'outline', color: string) => {
  const baseStyles =
    'inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border transition-colors';

  if (variant === 'outline') {
    switch (color) {
      case 'gray':
        return `${baseStyles} bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100`;
      case 'yellow':
        return `${baseStyles} bg-yellow-50 text-yellow-700 border-yellow-200 hover:bg-yellow-100`;
      default:
        return `${baseStyles} bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100`;
    }
  } else {
    switch (color) {
      case 'blue':
        return `${baseStyles} bg-blue-500 text-white border-blue-500 hover:bg-blue-600`;
      case 'yellow':
        return `${baseStyles} bg-yellow-500 text-white border-yellow-500 hover:bg-yellow-600`;
      case 'green':
        return `${baseStyles} bg-green-500 text-white border-green-500 hover:bg-green-600`;
      case 'red':
        return `${baseStyles} bg-red-500 text-white border-red-500 hover:bg-red-600`;
      default:
        return `${baseStyles} bg-gray-500 text-white border-gray-500 hover:bg-gray-600`;
    }
  }
};

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = getStatusConfig(status);
  const styles = getVariantStyles(config.variant, config.color);

  return <span className={`${styles} ${className || ''}`}>{config.text}</span>;
}

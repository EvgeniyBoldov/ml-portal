import React from 'react';
import Badge from '@shared/ui/Badge';
import { RAGStatus, statusToBadgeColor, statusToLabel } from '@shared/lib/ragStatus';

interface StatusButtonProps {
  status: RAGStatus;
  onClick: (event: React.MouseEvent) => void;
  className?: string;
  warning?: boolean;
}

const getStatusTone = (
  status: RAGStatus,
  warning?: boolean
): 'neutral' | 'info' | 'warn' | 'success' | 'danger' => {
  const color = statusToBadgeColor(status, warning);
  const toneMap = {
    green: 'success',
    blue: 'info',
    gray: 'neutral',
    red: 'danger',
    yellow: 'warn',
  };
  return toneMap[color] || 'neutral';
};

const getStatusText = (status: RAGStatus) => statusToLabel(status);

export default function StatusButton({
  status,
  onClick,
  className,
  warning,
}: StatusButtonProps) {
  const tone = getStatusTone(status, warning);
  const text = getStatusText(status);

  return (
    <Badge
      tone={tone}
      className={`cursor-pointer hover:opacity-80 transition-opacity ${className || ''}`}
      onClick={onClick}
      title="Нажмите для просмотра детального статуса"
      data-status-button="true"
      style={{ cursor: 'pointer' }}
    >
      {text}
    </Badge>
  );
}

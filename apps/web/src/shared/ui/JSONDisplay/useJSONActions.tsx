/**
 * useJSONActions - Hook for JSON display actions (copy, expand)
 * 
 * Returns actions that can be passed to Block headerActions
 */
import { useState } from 'react';

export interface JSONActionsProps {
  value: string;
  maxHeight?: string;
  onExpand?: () => void;
  isExpanded?: boolean;
}

export function useJSONActions({ 
  value, 
  maxHeight = '400px',
  onExpand,
  isExpanded = false 
}: JSONActionsProps) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(isExpanded);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const handleExpand = () => {
    if (onExpand) {
      onExpand();
    } else {
      setExpanded(!expanded);
    }
  };

  const actions = [
    {
      key: 'copy',
      label: copied ? 'Скопировано!' : 'Копировать',
      onClick: handleCopy,
      variant: 'outline' as const,
      size: 'small' as const,
    },
    {
      key: 'expand',
      label: expanded ? 'Свернуть' : 'Развернуть',
      onClick: handleExpand,
      variant: 'outline' as const,
      size: 'small' as const,
    },
  ];

  return {
    actions,
    isExpanded: expanded,
    setIsExpanded: setExpanded,
    maxHeight: expanded ? 'none' : maxHeight,
  };
}

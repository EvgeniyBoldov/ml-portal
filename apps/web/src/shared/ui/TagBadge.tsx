// apps/web/src/components/common/TagBadge.tsx
import React from 'react';

interface TagBadgeProps {
  tag: string;
  className?: string;
}

// Simple hash function for deterministic colors
const hashString = (str: string): number => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
};

const getTagColor = (tag: string) => {
  const hash = hashString(tag);

  // Define a palette of accessible colors
  const colors = [
    { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200' },
    { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200' },
    {
      bg: 'bg-yellow-100',
      text: 'text-yellow-800',
      border: 'border-yellow-200',
    },
    {
      bg: 'bg-purple-100',
      text: 'text-purple-800',
      border: 'border-purple-200',
    },
    { bg: 'bg-pink-100', text: 'text-pink-800', border: 'border-pink-200' },
    {
      bg: 'bg-indigo-100',
      text: 'text-indigo-800',
      border: 'border-indigo-200',
    },
    { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-200' },
    {
      bg: 'bg-orange-100',
      text: 'text-orange-800',
      border: 'border-orange-200',
    },
    { bg: 'bg-teal-100', text: 'text-teal-800', border: 'border-teal-200' },
    { bg: 'bg-cyan-100', text: 'text-cyan-800', border: 'border-cyan-200' },
  ];

  return colors[hash % colors.length];
};

export default function TagBadge({ tag, className }: TagBadgeProps) {
  const color = getTagColor(tag);

  return (
    <span
      className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${color.bg} ${color.text} ${color.border} hover:opacity-80 transition-opacity ${className || ''}`}
    >
      {tag}
    </span>
  );
}

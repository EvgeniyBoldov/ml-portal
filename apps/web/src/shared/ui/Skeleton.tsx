import React from 'react';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  variant?:
    | 'text'
    | 'circle'
    | 'rectangle'
    | 'avatar'
    | 'button'
    | 'badge'
    | 'card'
    | 'table';
  size?: 'short' | 'medium' | 'long';
  width?: string | number;
  height?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({
  variant = 'text',
  size = 'medium',
  width,
  height,
  className = '',
  style = {},
}: SkeletonProps) {
  const skeletonStyle = {
    ...style,
    ...(width && { width: typeof width === 'number' ? `${width}px` : width }),
    ...(height && {
      height: typeof height === 'number' ? `${height}px` : height,
    }),
  };

  return (
    <div
      className={`
        ${styles.skeleton}
        ${styles[variant]}
        ${variant === 'text' ? styles[size] : ''}
        ${className}
      `}
      style={skeletonStyle}
    />
  );
}

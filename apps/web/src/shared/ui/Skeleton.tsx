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

export interface SkeletonListProps {
  count?: number;
  variant?: 'vertical' | 'horizontal' | 'grid';
  children?: React.ReactNode;
  className?: string;
}

export function SkeletonList({
  count = 5,
  variant = 'vertical',
  children,
  className = '',
}: SkeletonListProps) {
  const items =
    children ||
    Array.from({ length: count }, (_, index) => <Skeleton key={index} />);

  return (
    <div className={`${styles.skeletonList} ${styles[variant]} ${className}`}>
      {items}
    </div>
  );
}

export interface SkeletonTableProps {
  rows?: number;
  columns?: number;
  showAvatar?: boolean;
  showBadge?: boolean;
  showActions?: boolean;
  className?: string;
}

export function SkeletonTable({
  rows = 5,
  columns = 4,
  showAvatar = false,
  showBadge = false,
  showActions = true,
  className = '',
}: SkeletonTableProps) {
  const renderRow = (rowIndex: number) => (
    <div key={rowIndex} className={styles.skeletonTableRow}>
      {showAvatar && (
        <div className={styles.skeletonTableCell}>
          <Skeleton variant="avatar" />
        </div>
      )}

      {Array.from({ length: columns }, (_, colIndex) => (
        <div key={colIndex} className={styles.skeletonTableCell}>
          <Skeleton
            variant="table"
            size={
              colIndex % 3 === 0
                ? 'short'
                : colIndex % 3 === 1
                  ? 'medium'
                  : 'long'
            }
          />
        </div>
      ))}

      {showBadge && (
        <div className={`${styles.skeletonTableCell} ${styles.badge}`}>
          <Skeleton variant="badge" />
        </div>
      )}

      {showActions && (
        <div className={`${styles.skeletonTableCell} ${styles.actions}`}>
          <Skeleton variant="button" />
        </div>
      )}
    </div>
  );

  return (
    <div className={`${styles.skeletonTable} ${className}`}>
      {Array.from({ length: rows }, (_, index) => renderRow(index))}
    </div>
  );
}

export interface SkeletonCardProps {
  showAvatar?: boolean;
  showActions?: boolean;
  className?: string;
}

export function SkeletonCard({
  showAvatar = true,
  showActions = true,
  className = '',
}: SkeletonCardProps) {
  return (
    <div className={`${styles.skeleton} ${styles.card} ${className}`}>
      <div style={{ padding: 'var(--spacing-md)' }}>
        {showAvatar && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              marginBottom: 'var(--spacing-sm)',
            }}
          >
            <Skeleton variant="avatar" />
            <div style={{ marginLeft: 'var(--spacing-sm)', flex: 1 }}>
              <Skeleton
                size="medium"
                style={{ marginBottom: 'var(--spacing-xs)' }}
              />
              <Skeleton size="short" />
            </div>
          </div>
        )}

        <div style={{ marginBottom: 'var(--spacing-sm)' }}>
          <Skeleton size="long" style={{ marginBottom: 'var(--spacing-xs)' }} />
          <Skeleton size="medium" />
        </div>

        {showActions && (
          <div
            style={{
              display: 'flex',
              gap: 'var(--spacing-sm)',
              justifyContent: 'flex-end',
            }}
          >
            <Skeleton variant="button" />
            <Skeleton variant="button" />
          </div>
        )}
      </div>
    </div>
  );
}

export default Skeleton;

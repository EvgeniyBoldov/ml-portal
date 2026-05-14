/**
 * TraceTree — рекурсивный рендерер иерархического трейса
 */

import * as React from 'react';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { TraceCard } from './TraceCard';
import styles from './TraceTree.module.css';

interface TraceTreeProps {
  root: TraceEntity;
  selectedId: string | null;
  onSelect: (entity: TraceEntity) => void;
  expandedIds: Set<string>;
  onToggleExpand: (id: string) => void;
}

function TreeNode({
  entity,
  selectedId,
  onSelect,
  expandedIds,
  onToggleExpand,
}: {
  entity: TraceEntity;
  selectedId: string | null;
  onSelect: (entity: TraceEntity) => void;
  expandedIds: Set<string>;
  onToggleExpand: (id: string) => void;
}): React.ReactElement {
  const hasChildren = entity.children.length > 0;
  const isExpanded = expandedIds.has(entity.id);
  const isSelected = selectedId === entity.id;

  const handleToggle = () => {
    onToggleExpand(entity.id);
  };

  const handleSelect = () => {
    onSelect(entity);
  };

  return (
    <div className={styles.node}>
      <TraceCard
        entity={entity}
        isExpanded={isExpanded}
        onToggle={handleToggle}
        onSelect={handleSelect}
        isSelected={isSelected}
        hasChildren={hasChildren}
      />

      {isExpanded && hasChildren && (
        <div className={styles.children}>
          {entity.children.map((child) => (
            <TreeNode
              key={child.id}
              entity={child}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function TraceTree({
  root,
  selectedId,
  onSelect,
  expandedIds,
  onToggleExpand,
}: TraceTreeProps): React.ReactElement {
  // Auto-expand root and first level by default
  React.useEffect(() => {
    if (expandedIds.size === 0 && root.children.length > 0) {
      // Expand root
      onToggleExpand(root.id);
      // Expand first-level entities
      root.children.forEach((child) => {
        onToggleExpand(child.id);
      });
    }
  }, [root, expandedIds.size, onToggleExpand]);

  return (
    <div className={styles.tree}>
      <TreeNode
        entity={root}
        selectedId={selectedId}
        onSelect={onSelect}
        expandedIds={expandedIds}
        onToggleExpand={onToggleExpand}
      />
    </div>
  );
}

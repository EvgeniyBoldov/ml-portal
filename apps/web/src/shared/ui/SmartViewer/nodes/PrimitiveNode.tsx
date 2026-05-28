import { useState } from 'react';
import { GutterRow } from '../GutterRow';
import styles from '../SmartViewer.module.css';
import type { BooleanParsedNode, NullParsedNode, NumberParsedNode } from './types';

interface PrimitiveNodeProps {
  name?: string;
  node: NumberParsedNode | BooleanParsedNode | NullParsedNode;
  depth: number;
}

export function PrimitiveNode({ name, node, depth }: PrimitiveNodeProps) {
  const [, forceRender] = useState(0);
  void forceRender;

  const renderValue = () => {
    if (node.type === 'null') {
      return <span className={styles.valueNull}>null</span>;
    }
    if (node.type === 'boolean') {
      return (
        <span className={node.value ? styles.valueTrue : styles.valueFalse}>
          {String(node.value)}
        </span>
      );
    }
    return <span className={styles.valueNumber}>{node.value}</span>;
  };

  return (
    <GutterRow depth={depth} foldable={false} folded={false}>
      {name !== undefined && <span className={styles.key}>{name}: </span>}
      {renderValue()}
    </GutterRow>
  );
}

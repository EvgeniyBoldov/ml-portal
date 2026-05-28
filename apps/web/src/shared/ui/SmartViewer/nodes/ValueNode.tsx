import { useState } from 'react';
import { GutterRow } from '../GutterRow';
import styles from '../SmartViewer.module.css';
import type { ArrayParsedNode, ObjectParsedNode, ParsedNode } from './types';
import { PrimitiveNode } from './PrimitiveNode';
import { StringNode } from './StringNode';

interface ValueNodeProps {
  name?: string;
  node: ParsedNode;
  depth: number;
  skipBrace?: boolean;
}

function ObjectNodeInner({ name, node, depth }: { name?: string; node: ObjectParsedNode; depth: number }) {
  const [folded, setFolded] = useState(false);
  const nameSpan = name !== undefined ? <span className={styles.key}>{name}: </span> : null;

  if (node.entries.length === 0) {
    return (
      <GutterRow depth={depth} foldable={false} folded={false}>
        {nameSpan}
        <span className={styles.bracket}>{'{}'}</span>
      </GutterRow>
    );
  }

  if (folded) {
    return (
      <GutterRow depth={depth} foldable onToggle={() => setFolded(false)} folded>
        {nameSpan}
        <span className={styles.bracket}>{'{…}'}</span>
        <span className={styles.badge}>{node.entries.length} keys</span>
      </GutterRow>
    );
  }

  return (
    <>
      <GutterRow depth={depth} foldable onToggle={() => setFolded(true)} folded={false}>
        {nameSpan}
        <span className={styles.bracket}>{'{'}</span>
      </GutterRow>
      {node.entries.map(({ key, node: child }) => (
        <ValueNode key={key} name={key} node={child} depth={depth + 1} />
      ))}
      <GutterRow depth={depth} foldable={false} folded={false} isClosing>
        <span className={styles.bracket}>{'}'}</span>
      </GutterRow>
    </>
  );
}

function ArrayNodeInner({ name, node, depth }: { name?: string; node: ArrayParsedNode; depth: number }) {
  const [folded, setFolded] = useState(false);
  const nameSpan = name !== undefined ? <span className={styles.key}>{name}: </span> : null;

  if (node.items.length === 0) {
    return (
      <GutterRow depth={depth} foldable={false} folded={false}>
        {nameSpan}
        <span className={styles.bracket}>{'[]'}</span>
      </GutterRow>
    );
  }

  if (folded) {
    return (
      <GutterRow depth={depth} foldable onToggle={() => setFolded(false)} folded>
        {nameSpan}
        <span className={styles.bracket}>{'[…]'}</span>
        <span className={styles.badge}>{node.items.length} items</span>
      </GutterRow>
    );
  }

  return (
    <>
      <GutterRow depth={depth} foldable onToggle={() => setFolded(true)} folded={false}>
        {nameSpan}
        <span className={styles.bracket}>{'['}</span>
      </GutterRow>
      {node.items.map((child, i) => (
        <ValueNode key={i} node={child} depth={depth + 1} />
      ))}
      <GutterRow depth={depth} foldable={false} folded={false} isClosing>
        <span className={styles.bracket}>{']'}</span>
      </GutterRow>
    </>
  );
}

export function ValueNode({ name, node, depth, skipBrace = false }: ValueNodeProps) {
  if (node.type === 'object') {
    if (skipBrace) {
      return (
        <>
          {node.entries.map(({ key, node: child }) => (
            <ValueNode key={key} name={key} node={child} depth={depth} />
          ))}
        </>
      );
    }
    return <ObjectNodeInner name={name} node={node} depth={depth} />;
  }

  if (node.type === 'array') {
    if (skipBrace) {
      return (
        <>
          {node.items.map((child, i) => (
            <ValueNode key={i} node={child} depth={depth} />
          ))}
        </>
      );
    }
    return <ArrayNodeInner name={name} node={node} depth={depth} />;
  }

  if (
    node.type === 'string' ||
    node.type === 'multiline' ||
    node.type === 'embedded_json'
  ) {
    return <StringNode name={name} node={node} depth={depth} />;
  }

  if (
    node.type === 'number' ||
    node.type === 'boolean' ||
    node.type === 'null'
  ) {
    return <PrimitiveNode name={name} node={node} depth={depth} />;
  }

  return null;
}

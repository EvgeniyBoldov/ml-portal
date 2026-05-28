import { useState } from 'react';
import { GutterRow } from '../GutterRow';
import styles from '../SmartViewer.module.css';
import type { EmbeddedJsonParsedNode, MultilineParsedNode, StringParsedNode } from './types';
import { ValueNode } from './ValueNode';

interface StringNodeProps {
  name?: string;
  node: StringParsedNode | MultilineParsedNode | EmbeddedJsonParsedNode;
  depth: number;
}

export function StringNode({ name, node, depth }: StringNodeProps) {
  const [folded, setFolded] = useState(false);

  const nameSpan = name !== undefined ? <span className={styles.key}>{name}: </span> : null;

  if (node.type === 'embedded_json') {
    if (folded) {
      const hint = node.parsed.type === 'array' ? '[…]' : '{…}';
      return (
        <GutterRow depth={depth} foldable onToggle={() => setFolded(false)} folded>
          {nameSpan}
          <span className={styles.bracket}>{hint}</span>
        </GutterRow>
      );
    }
    return (
      <>
        <GutterRow depth={depth} foldable onToggle={() => setFolded(true)} folded={false}>
          {nameSpan}
          <span className={styles.bracket}>{node.parsed.type === 'array' ? '[' : '{'}</span>
        </GutterRow>
        <ValueNode node={node.parsed} depth={depth + 1} skipBrace />
        <GutterRow depth={depth} foldable={false} folded={false} isClosing>
          <span className={styles.bracket}>{node.parsed.type === 'array' ? ']' : '}'}</span>
        </GutterRow>
      </>
    );
  }

  if (node.type === 'multiline') {
    const lineCount = node.lines.length;
    if (folded) {
      const firstLine = node.lines[0] ?? '';
      return (
        <GutterRow depth={depth} foldable onToggle={() => setFolded(false)} folded>
          {nameSpan}
          <span className={styles.valueString}>{firstLine}</span>
          <span className={styles.badge}>{lineCount} lines</span>
        </GutterRow>
      );
    }
    return (
      <>
        <GutterRow depth={depth} foldable onToggle={() => setFolded(true)} folded={false}>
          {nameSpan}
          <span className={styles.valueString}>{node.lines[0] ?? ''}</span>
        </GutterRow>
        {node.lines.slice(1).map((line, i) => (
          <GutterRow key={i} depth={depth} foldable={false} folded={false}>
            <span className={styles.valueString}>{line || '\u00A0'}</span>
          </GutterRow>
        ))}
      </>
    );
  }

  return (
    <GutterRow depth={depth} foldable={false} folded={false}>
      {nameSpan}
      <span className={styles.valueString}>{node.value}</span>
    </GutterRow>
  );
}

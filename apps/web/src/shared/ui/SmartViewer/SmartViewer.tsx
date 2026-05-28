import { useSmartParse } from './useSmartParse';
import { ValueNode } from './nodes/ValueNode';
import styles from './SmartViewer.module.css';

interface SmartViewerProps {
  value: unknown;
  className?: string;
}

export function SmartViewer({ value, className }: SmartViewerProps) {
  const node = useSmartParse(value);

  return (
    <div className={`${styles.root}${className ? ` ${className}` : ''}`}>
      <ValueNode node={node} depth={0} />
    </div>
  );
}

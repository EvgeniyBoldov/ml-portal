import type { ReactNode } from 'react';
import { InspectorHeader, InspectorPanel } from '@/shared/ui/Inspector';

interface BaseInspectorShellProps {
  tone: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
  kindLabel: string;
  title: string;
  meta?: string;
  children: ReactNode;
}

export function BaseInspectorShell({
  tone,
  kindLabel,
  title,
  meta,
  children,
}: BaseInspectorShellProps) {
  return (
    <InspectorPanel
      header={<InspectorHeader tone={tone} kindLabel={kindLabel} title={title} meta={meta} />}
    >
      {children}
    </InspectorPanel>
  );
}

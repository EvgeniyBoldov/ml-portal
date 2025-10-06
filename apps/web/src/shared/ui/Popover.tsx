import React, { useEffect, useRef, useState } from 'react';

interface PopoverProps {
  trigger?: React.ReactNode;
  content: React.ReactNode;
  align?: 'start' | 'end';
  // New API for controlled popover
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  anchor?: { x: number; y: number };
}

export default function Popover({
  trigger,
  content,
  align = 'start',
  open: controlledOpen,
  onOpenChange,
  anchor,
}: PopoverProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  
  // Use controlled state if provided, otherwise use internal state
  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen;
  const setIsOpen = onOpenChange || setInternalOpen;

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as any)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', onDoc);
      return () => document.removeEventListener('mousedown', onDoc);
    }
  }, [isOpen, setIsOpen]);

  // If using anchor positioning (for action menus)
  if (anchor) {
    return (
      <>
        {isOpen && (
          <div
            style={{
              position: 'fixed',
              left: anchor.x,
              top: anchor.y,
              zIndex: 1000,
              background: 'var(--panel)',
              border: '1px solid rgba(255,255,255,.12)',
              borderRadius: 8,
              padding: 4,
              boxShadow: '0 6px 24px rgba(0,0,0,.35)',
            }}
          >
            {content}
          </div>
        )}
      </>
    );
  }

  // Original trigger-based API
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {trigger && (
        <div onClick={() => setIsOpen(v => !v)}>{trigger}</div>
      )}
      {isOpen && (
        <div
          style={
            {
              position: 'absolute',
              top: '100%',
              [align === 'end' ? 'right' : 'left']: 0,
              zIndex: 10,
              background: 'var(--panel)',
              border: '1px solid rgba(255,255,255,.12)',
              borderRadius: 8,
              padding: 4,
              boxShadow: '0 6px 24px rgba(0,0,0,.35)',
            } as any
          }
        >
          {content}
        </div>
      )}
    </div>
  );
}

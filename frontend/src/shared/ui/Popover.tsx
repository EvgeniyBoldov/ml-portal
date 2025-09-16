import React, { useEffect, useRef, useState } from 'react';

export default function Popover({
  trigger,
  content,
  align = 'start',
}: {
  trigger: React.ReactNode;
  content: React.ReactNode;
  align?: 'start' | 'end';
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as any)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div onClick={() => setOpen(v => !v)}>{trigger}</div>
      {open && (
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

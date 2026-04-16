import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

type PopoverAlign = 'start' | 'end';
type PopoverSide = 'top' | 'bottom';

interface PopoverProps {
  trigger?: React.ReactNode;
  content: React.ReactNode;
  align?: PopoverAlign;
  side?: PopoverSide;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  anchor?: { x: number; y: number };
  id?: string;
  ariaLabel?: string;
  'aria-haspopup'?: boolean;
}

const POPOVER_OFFSET = 8;

export default function Popover({
  trigger,
  content,
  align = 'start',
  side = 'bottom',
  open,
  onOpenChange,
  anchor,
  id,
  ariaLabel,
  'aria-haspopup': ariaHaspopup = true,
}: PopoverProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [placement, setPlacement] = useState<React.CSSProperties | null>(null);
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? !!open : internalOpen;

  const setOpen = useCallback(
    (next: boolean) => {
      if (isControlled) {
        onOpenChange?.(next);
        return;
      }
      setInternalOpen(next);
    },
    [isControlled, onOpenChange]
  );

  const updatePlacement = useCallback(() => {
    if (!isOpen) {
      setPlacement(null);
      return;
    }

    if (anchor) {
      setPlacement({
        position: 'fixed',
        top: anchor.y,
        left: anchor.x,
        transform: 'translate3d(0, 0, 0)',
      });
      return;
    }

    const triggerNode = triggerRef.current;
    if (!triggerNode) {
      setPlacement(null);
      return;
    }

    const rect = triggerNode.getBoundingClientRect();
    const left = align === 'end' ? rect.right : rect.left;
    const top = side === 'top' ? rect.top - POPOVER_OFFSET : rect.bottom + POPOVER_OFFSET;

    setPlacement({
      position: 'fixed',
      left,
      top,
      transform: align === 'end' ? 'translate3d(-100%, 0, 0)' : 'translate3d(0, 0, 0)',
    });
  }, [align, anchor, isOpen, side]);

  useLayoutEffect(() => {
    updatePlacement();
  }, [updatePlacement]);

  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        popoverRef.current?.contains(target) ||
        triggerRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    const handleRelayout = () => {
      updatePlacement();
    };

    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    window.addEventListener('resize', handleRelayout);
    window.addEventListener('scroll', handleRelayout, true);

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
      window.removeEventListener('resize', handleRelayout);
      window.removeEventListener('scroll', handleRelayout, true);
    };
  }, [isOpen, setOpen, updatePlacement]);

  const handleTriggerClick = useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation();
      setOpen(!isOpen);
    },
    [isOpen, setOpen]
  );

  const handleTriggerKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        event.stopPropagation();
        setOpen(!isOpen);
      }
    },
    [isOpen, setOpen]
  );

  const handleContentMouseDown = useCallback((event: React.MouseEvent) => {
    event.stopPropagation();
  }, []);

  const handleContentClick = useCallback((event: React.MouseEvent) => {
    event.stopPropagation();
  }, []);

  return (
    <div ref={triggerRef} id={id} style={{ position: 'relative', display: 'inline-flex' }}>
      {trigger && (
        <div
          role="button"
          tabIndex={0}
          aria-haspopup={ariaHaspopup}
          aria-expanded={isOpen}
          aria-label={ariaLabel}
          onClick={event => void handleTriggerClick(event)}
          onKeyDown={event => void handleTriggerKeyDown(event)}
        >
          {trigger}
        </div>
      )}

      {isOpen && placement && (
        <div
          ref={popoverRef}
          role="menu"
          aria-hidden={!isOpen}
          onMouseDown={event => void handleContentMouseDown(event)}
          onClick={event => void handleContentClick(event)}
          style={{
            zIndex: 1010,
            minWidth: 160,
            maxWidth: 320,
            padding: 8,
            borderRadius: 8,
            background: 'var(--panel, #1f2933)',
            border: '1px solid var(--border-color, rgba(255, 255, 255, 0.12))',
            boxShadow: '0 12px 32px rgba(15, 23, 42, 0.35)',
            ...placement,
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
}

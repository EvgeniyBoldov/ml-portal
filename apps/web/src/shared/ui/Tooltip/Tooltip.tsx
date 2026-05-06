import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import styles from './Tooltip.module.css';

type TooltipPosition = 'top' | 'bottom' | 'left' | 'right';

interface TooltipCoords {
  top: number;
  left: number;
  position: TooltipPosition;
}

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  /** Preferred position, auto-flips if no space */
  position?: TooltipPosition;
  delay?: number;
  className?: string;
  /** Max width of tooltip in px */
  maxWidth?: number;
}

const GAP = 8;
const TOOLTIP_W = 280;
const TOOLTIP_H = 120;

function calcPosition(
  triggerRect: DOMRect,
  preferred: TooltipPosition,
  tooltipW: number,
  tooltipH: number,
): TooltipCoords {
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  const positions: TooltipPosition[] = [
    preferred,
    preferred === 'top' ? 'bottom' : preferred === 'bottom' ? 'top' : preferred === 'left' ? 'right' : 'left',
    'top',
    'bottom',
    'left',
    'right',
  ];

  for (const pos of positions) {
    let top = 0;
    let left = 0;

    if (pos === 'top') {
      top = triggerRect.top - tooltipH - GAP;
      left = triggerRect.left + triggerRect.width / 2 - tooltipW / 2;
    } else if (pos === 'bottom') {
      top = triggerRect.bottom + GAP;
      left = triggerRect.left + triggerRect.width / 2 - tooltipW / 2;
    } else if (pos === 'left') {
      top = triggerRect.top + triggerRect.height / 2 - tooltipH / 2;
      left = triggerRect.left - tooltipW - GAP;
    } else {
      top = triggerRect.top + triggerRect.height / 2 - tooltipH / 2;
      left = triggerRect.right + GAP;
    }

    // Clamp to viewport
    const clampedLeft = Math.max(8, Math.min(left, vw - tooltipW - 8));
    const clampedTop = Math.max(8, Math.min(top, vh - tooltipH - 8));

    // Check if fits without heavy clamping
    const fits = (
      top >= 4 && top + tooltipH <= vh - 4 &&
      left >= 4 && left + tooltipW <= vw - 4
    );

    if (fits || pos === positions[positions.length - 1]) {
      return { top: clampedTop, left: clampedLeft, position: pos };
    }
  }

  return { top: 0, left: 0, position: preferred };
}

export function Tooltip({
  content,
  children,
  position = 'top',
  delay = 150,
  className = '',
  maxWidth = TOOLTIP_W,
}: TooltipProps) {
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  const showTooltip = useCallback(() => {
    timeoutRef.current = setTimeout(() => {
      if (triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect();
        setCoords(calcPosition(rect, position, maxWidth, TOOLTIP_H));
      }
    }, delay);
  }, [position, delay, maxWidth]);

  const hideTooltip = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setCoords(null);
  }, []);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return (
    <div
      ref={triggerRef}
      className={[styles.wrapper, className].join(' ')}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      {coords && content && createPortal(
        <div
          className={[styles.tooltip, styles[coords.position]].join(' ')}
          style={{ top: coords.top, left: coords.left, maxWidth }}
          role="tooltip"
        >
          {content}
          <div className={styles.arrow} />
        </div>,
        document.body,
      )}
    </div>
  );
}

export default Tooltip;
